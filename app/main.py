from datetime import datetime, timedelta, timezone
from pathlib import Path
import csv, io, json, secrets, shutil
from fastapi import FastAPI, Request, Form, Depends, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, func, or_, text
from sqlalchemy.orm import Session
from .config import settings
from .db import Base, engine, get_db, SessionLocal
from .models import *
from .security import hash_password, verify_password, new_token, token_hash, encode_session, decode_session
from .services import audit, queue_email
from .storage import storage
from .scanner import scan_file
from .entra import oauth, configured as entra_configured

VERSION = "0.6.0"
BASE = Path(__file__).resolve().parent
app = FastAPI(title=settings.app_name, version=VERSION)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=settings.cookie_secure, same_site="lax")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[x.strip() for x in settings.trusted_hosts.split(",") if x.strip()])

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed = {x.strip().rstrip("/") for x in settings.allowed_origins.split(",") if x.strip()}
            if origin and origin.rstrip("/") not in allowed:
                return HTMLResponse("Request origin is not permitted.", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self' 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

app.add_middleware(SecurityHeadersMiddleware)
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def now(): return datetime.now(timezone.utc)
def naive_now(): return now().replace(tzinfo=None)
def unexpired(v): return bool(v and v.replace(tzinfo=None) > naive_now())
def enum_value(v, e, field):
    if v not in {x.value for x in e}: raise HTTPException(400, f"Invalid {field}.")
    return v

def current_user(request: Request, db: Session = Depends(get_db)):
    uid = decode_session(request.cookies.get("session", "")); u = db.get(User, uid) if uid else None
    if not u or not u.is_active: raise HTTPException(303, headers={"Location":"/login"})
    return u

def roles(*allowed):
    def dep(u=Depends(current_user)):
        if u.role not in allowed: raise HTTPException(403, "Insufficient permission")
        return u
    return dep

def render(request, name, user=None, **ctx):
    return templates.TemplateResponse(request=request, name=name, context={"user":user,"app_name":settings.app_name,"version":VERSION,"can_edit":bool(user and user.role in {"owner","admin","researcher"}),"entra_enabled":entra_configured(),"local_login_enabled":settings.local_login_enabled,**ctx})

def project(db,i,o):
    r=db.scalar(select(Project).where(Project.id==i,Project.organisation_id==o))
    if not r: raise HTTPException(404)
    return r

def study(db,i,o):
    r=db.scalar(select(Study).where(Study.id==i,Study.organisation_id==o))
    if not r: raise HTTPException(404)
    return r

def participant(db,i,o):
    r=db.scalar(select(Participant).where(Participant.id==i,Participant.organisation_id==o))
    if not r: raise HTTPException(404)
    return r


def study_permission(db: Session, user: User, study_row: Study) -> str | None:
    if user.role in {"owner", "admin"}:
        return "manage"
    if study_row.created_by_id == user.id:
        return "edit"
    access = db.scalar(select(StudyAccess).where(StudyAccess.study_id == study_row.id, StudyAccess.user_id == user.id, StudyAccess.organisation_id == user.organisation_id))
    if access:
        return access.permission
    return "view" if user.role == "observer" else None


def require_study_permission(db: Session, user: User, study_row: Study, edit: bool = False):
    permission = study_permission(db, user, study_row)
    if not permission or (edit and permission not in {"edit", "manage"}):
        raise HTTPException(403, "You do not have access to this study.")
    return permission

def portal_invitation(db, token):
    inv=db.scalar(select(ParticipantInvitation).where(ParticipantInvitation.token_hash==token_hash(token)))
    if not inv or inv.revoked_at or not unexpired(inv.expires_at): raise HTTPException(400,"This participant link is invalid or expired.")
    return inv

def paginate(stmt, db, page, per=25):
    page=max(1,page); total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows=db.scalars(stmt.offset((page-1)*per).limit(per)).all()
    return rows,total,max(1,(total+per-1)//per)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    # Safe additive migration for databases created by v0.2.x.
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as c:
            cols={r[1] for r in c.execute(text("PRAGMA table_info(studies)"))}
            if "demographics_schema_json" not in cols: c.execute(text("ALTER TABLE studies ADD COLUMN demographics_schema_json TEXT DEFAULT '[]'"))
            user_cols={r[1] for r in c.execute(text("PRAGMA table_info(users)"))}
            if "external_provider" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN external_provider VARCHAR(40)"))
            if "external_subject" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN external_subject VARCHAR(255)"))
            if "last_login_at" not in user_cols: c.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME"))
            evidence_cols={r[1] for r in c.execute(text("PRAGMA table_info(evidence_files)"))}
            if "sha256_hex" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN sha256_hex VARCHAR(64) DEFAULT ''"))
            if "scan_status" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_status VARCHAR(30) DEFAULT 'pending'"))
            if "scan_detail" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_detail TEXT DEFAULT ''"))
            if "storage_provider" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN storage_provider VARCHAR(30) DEFAULT 'local'"))
            if "blob_uri" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN blob_uri TEXT DEFAULT ''"))
            if "scan_completed_at" not in evidence_cols: c.execute(text("ALTER TABLE evidence_files ADD COLUMN scan_completed_at DATETIME"))
    with SessionLocal() as db:
        if settings.seed_demo_data and not db.scalar(select(func.count(User.id))):
            org=Organisation(name="Politis Demo Council",slug="politis-demo"); db.add(org); db.flush()
            u=User(organisation_id=org.id,name="Platform Owner",email="admin@politis.local",password_hash=hash_password("PolitisDemo!"),role="owner"); db.add(u); db.flush()
            p=Project(organisation_id=org.id,title="Town Centre Experience",code="TCX-001",description="Demonstration civic intelligence project.",status="live",created_by_id=u.id); db.add(p); db.flush()
            s=Study(organisation_id=org.id,project_id=p.id,title="Seven-day town centre diary",code="TCX-D01",description="A demonstration longitudinal diary study.",methodology="diary",status="recruiting",created_by_id=u.id); db.add(s); db.flush()
            db.add(Activity(organisation_id=org.id,study_id=s.id,title="First impressions",prompt="Tell us about your latest visit to the town centre.",activity_type="long_text",position=1))
            audit(db,org.id,u.id,"platform.seeded","organisation",org.id,"Initial demonstration tenant created"); db.commit()

@app.get("/health")
def health(): return {"status":"ok","version":VERSION}
@app.get("/login",response_class=HTMLResponse)
def login_page(request:Request): return render(request,"login.html")
@app.post("/login")
def login(request:Request,email:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    if not settings.local_login_enabled: return render(request,"login.html",error="Password sign-in is disabled. Use Microsoft sign-in.")
    u=db.scalar(select(User).where(User.email==email.lower().strip(),User.is_active==True))
    if not u or not u.password_hash or not verify_password(password,u.password_hash): return render(request,"login.html",error="Email or password is incorrect.")
    u.last_login_at=now(); audit(db,u.organisation_id,u.id,"auth.login","user",u.id); db.commit(); r=RedirectResponse("/",303); r.set_cookie("session",encode_session(u.id),httponly=True,samesite="strict",secure=settings.cookie_secure,max_age=43200); return r

@app.get("/auth/entra/login")
async def entra_login(request: Request):
    if not entra_configured():
        raise HTTPException(503, "Microsoft sign-in is not configured.")
    redirect_uri = f"{settings.base_url.rstrip('/')}/auth/entra/callback"
    return await oauth.entra.authorize_redirect(request, redirect_uri)

@app.get("/auth/entra/callback")
async def entra_callback(request: Request, db: Session = Depends(get_db)):
    if not entra_configured():
        raise HTTPException(503, "Microsoft sign-in is not configured.")
    try:
        token = await oauth.entra.authorize_access_token(request)
    except Exception:
        return render(request, "login.html", error="Microsoft sign-in could not be completed.")
    claims = token.get("userinfo") or {}
    subject = claims.get("sub") or claims.get("oid")
    email = (claims.get("preferred_username") or claims.get("email") or "").lower().strip()
    name = claims.get("name") or email
    tenant = claims.get("tid")
    if not subject or not email or (settings.entra_tenant_id and tenant and tenant != settings.entra_tenant_id):
        return render(request, "login.html", error="Microsoft account details could not be verified.")
    allowed = {x.strip().lower() for x in settings.entra_allowed_domains.split(",") if x.strip()}
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if allowed and domain not in allowed:
        return render(request, "login.html", error="This Microsoft account is not permitted for this service.")
    user = db.scalar(select(User).where(User.external_provider == "entra", User.external_subject == subject, User.is_active == True))
    if not user:
        user = db.scalar(select(User).where(User.email == email, User.is_active == True))
        if user:
            user.external_provider = "entra"
            user.external_subject = subject
        elif settings.entra_auto_provision and settings.entra_default_organisation_slug:
            org = db.scalar(select(Organisation).where(Organisation.slug == settings.entra_default_organisation_slug))
            if not org:
                return render(request, "login.html", error="The configured organisation could not be found.")
            role = settings.entra_default_role if settings.entra_default_role in {"owner","admin","researcher","observer"} else "researcher"
            user = User(organisation_id=org.id, name=name[:120], email=email, password_hash=None, role=role, is_active=True, external_provider="entra", external_subject=subject)
            db.add(user); db.flush()
        else:
            return render(request, "login.html", error="Your Microsoft account has not been invited to this workspace.")
    user.name = name[:120] or user.name
    user.last_login_at = now()
    audit(db, user.organisation_id, user.id, "auth.entra_login", "user", user.id)
    db.commit()
    response = RedirectResponse("/", 303)
    response.set_cookie("session", encode_session(user.id), httponly=True, samesite="lax", secure=settings.cookie_secure, max_age=43200)
    return response

@app.post("/logout")
def logout(): r=RedirectResponse("/login",303); r.delete_cookie("session"); return r

@app.get("/forgot-password",response_class=HTMLResponse)
def forgot_page(request:Request): return render(request,"forgot_password.html")
@app.post("/forgot-password",response_class=HTMLResponse)
def forgot(request:Request,email:str=Form(...),db:Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==email.lower().strip(),User.is_active==True))
    if u:
        raw=new_token(); db.add(PasswordReset(user_id=u.id,token_hash=token_hash(raw),expires_at=now()+timedelta(hours=1)))
        queue_email(db,u.organisation_id,u.email,"Reset your PCIP password",f"Reset your password: {settings.base_url}/reset-password?token={raw}"); audit(db,u.organisation_id,u.id,"auth.password_reset_requested","user",u.id); db.commit()
    return render(request,"forgot_password.html",sent=True)
@app.get("/reset-password",response_class=HTMLResponse)
def reset_page(request:Request,token:str="",db:Session=Depends(get_db)):
    row=db.scalar(select(PasswordReset).where(PasswordReset.token_hash==token_hash(token))); valid=bool(row and not row.used_at and unexpired(row.expires_at)); return render(request,"reset_password.html",token=token,valid=valid)
@app.post("/reset-password")
def reset_password(token:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    row=db.scalar(select(PasswordReset).where(PasswordReset.token_hash==token_hash(token)))
    if not row or row.used_at or not unexpired(row.expires_at): raise HTTPException(400,"Reset link is invalid or expired.")
    if len(password)<10: raise HTTPException(400,"Password must contain at least 10 characters.")
    u=db.get(User,row.user_id); u.password_hash=hash_password(password); row.used_at=now(); audit(db,u.organisation_id,u.id,"auth.password_reset","user",u.id); db.commit(); return RedirectResponse("/login",303)

@app.get("/",response_class=HTMLResponse)
def dashboard(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    o=u.organisation_id
    metrics={"projects":db.scalar(select(func.count(Project.id)).where(Project.organisation_id==o)) or 0,"studies":db.scalar(select(func.count(Study.id)).where(Study.organisation_id==o)) or 0,"participants":db.scalar(select(func.count(Participant.id)).where(Participant.organisation_id==o)) or 0,"active":db.scalar(select(func.count(Participant.id)).where(Participant.organisation_id==o,Participant.status=="active")) or 0,"invitations":db.scalar(select(func.count(ParticipantInvitation.id)).where(ParticipantInvitation.organisation_id==o,ParticipantInvitation.accepted_at.is_(None),ParticipantInvitation.revoked_at.is_(None))) or 0,"submissions":db.scalar(select(func.count(ActivityResponse.id)).where(ActivityResponse.organisation_id==o,ActivityResponse.status=="submitted")) or 0}
    studies=db.scalars(select(Study).where(Study.organisation_id==o).order_by(Study.updated_at.desc()).limit(6)).all(); pmap={p.id:p for p in db.scalars(select(Project).where(Project.organisation_id==o)).all()}
    return render(request,"dashboard.html",user=u,metrics=metrics,studies=studies,project_map=pmap)

@app.get("/projects",response_class=HTMLResponse)
def projects(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(Project).where(Project.organisation_id==u.organisation_id).order_by(Project.updated_at.desc())).all(); counts=dict(db.execute(select(Study.project_id,func.count(Study.id)).where(Study.organisation_id==u.organisation_id).group_by(Study.project_id)).all()); return render(request,"projects.html",user=u,projects=rows,counts=counts,statuses=[x.value for x in ProjectStatus])
@app.post("/projects")
def create_project(title:str=Form(...),code:str=Form(...),description:str=Form(""),status_value:str=Form("draft"),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    enum_value(status_value,ProjectStatus,"project status"); row=Project(organisation_id=u.organisation_id,title=title.strip(),code=code.strip().upper(),description=description.strip(),status=status_value,created_by_id=u.id); db.add(row)
    try: db.flush(); audit(db,u.organisation_id,u.id,"project.created","project",row.id,row.title); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Project code must be unique.")
    return RedirectResponse(f"/projects/{row.id}",303)
@app.get("/projects/{project_id}",response_class=HTMLResponse)
def project_detail(project_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); studies=db.scalars(select(Study).where(Study.project_id==p.id,Study.organisation_id==u.organisation_id).order_by(Study.updated_at.desc())).all(); return render(request,"project_detail.html",user=u,project=p,studies=studies,statuses=[x.value for x in StudyStatus])
@app.post("/projects/{project_id}/edit")
def edit_project(project_id:int,title:str=Form(...),description:str=Form(""),status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); enum_value(status_value,ProjectStatus,"project status"); p.title=title.strip(); p.description=description.strip(); p.status=status_value; audit(db,u.organisation_id,u.id,"project.updated","project",p.id,p.title); db.commit(); return RedirectResponse(f"/projects/{p.id}",303)
@app.post("/projects/{project_id}/status")
def update_project_status(project_id:int,status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)): return edit_project(project_id,project(db,project_id,u.organisation_id).title,project(db,project_id,u.organisation_id).description,status_value,u,db)

@app.get("/studies",response_class=HTMLResponse)
def studies_page(request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Study).where(Study.organisation_id==u.organisation_id)
    if u.role not in {"owner","admin","observer"}:
        permitted_ids=select(StudyAccess.study_id).where(StudyAccess.organisation_id==u.organisation_id,StudyAccess.user_id==u.id)
        stmt=stmt.where(or_(Study.created_by_id==u.id,Study.id.in_(permitted_ids)))
    rows=db.scalars(stmt.order_by(Study.updated_at.desc())).all(); projects={p.id:p for p in db.scalars(select(Project).where(Project.organisation_id==u.organisation_id)).all()}; counts=dict(db.execute(select(StudyEnrolment.study_id,func.count()).where(StudyEnrolment.organisation_id==u.organisation_id).group_by(StudyEnrolment.study_id)).all()); return render(request,"studies.html",user=u,studies=rows,projects=projects,enrolment_counts=counts)
@app.post("/projects/{project_id}/studies")
def create_study(project_id:int,title:str=Form(...),code:str=Form(...),description:str=Form(""),methodology:str=Form("diary"),status_value:str=Form("draft"),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    p=project(db,project_id,u.organisation_id); enum_value(status_value,StudyStatus,"study status"); allowed={"diary","walk_along","interview","focus_group","co_design","mixed_method"}
    if methodology not in allowed: raise HTTPException(400,"Invalid methodology.")
    s=Study(organisation_id=u.organisation_id,project_id=p.id,title=title.strip(),code=code.strip().upper(),description=description.strip(),methodology=methodology,status=status_value,created_by_id=u.id); db.add(s)
    try: db.flush(); audit(db,u.organisation_id,u.id,"study.created","study",s.id,s.title); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Study code must be unique.")
    return RedirectResponse(f"/studies/{s.id}",303)
@app.get("/studies/{study_id}",response_class=HTMLResponse)
def study_detail(study_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); permission=require_study_permission(db,u,s); p=project(db,s.project_id,u.organisation_id); acts=db.scalars(select(Activity).where(Activity.study_id==s.id,Activity.organisation_id==u.organisation_id).order_by(Activity.position)).all(); ens=db.scalars(select(StudyEnrolment).where(StudyEnrolment.study_id==s.id,StudyEnrolment.organisation_id==u.organisation_id)).all(); ps={x.id:x for x in db.scalars(select(Participant).where(Participant.organisation_id==u.organisation_id)).all()}; invs=db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.study_id==s.id,ParticipantInvitation.organisation_id==u.organisation_id).order_by(ParticipantInvitation.created_at.desc())).all(); latest={}
    for i in invs: latest.setdefault(i.participant_id,i)
    available=[x for x in ps.values() if x.id not in {e.participant_id for e in ens}]
    response_counts=dict(db.execute(select(ActivityResponse.activity_id,func.count()).where(ActivityResponse.study_id==s.id,ActivityResponse.status=="submitted").group_by(ActivityResponse.activity_id)).all())
    access_rows=db.scalars(select(StudyAccess).where(StudyAccess.study_id==s.id,StudyAccess.organisation_id==u.organisation_id)).all(); access_map={a.user_id:a for a in access_rows}; team=db.scalars(select(User).where(User.organisation_id==u.organisation_id,User.is_active==True).order_by(User.name)).all()
    return render(request,"study_detail.html",user=u,study=s,project=p,activities=acts,enrolments=ens,participants=ps,available=available,latest_invites=latest,response_counts=response_counts,study_permission=permission,team=team,access_map=access_map,can_edit=permission in {"edit","manage"},activity_types=["short_text","long_text","single_choice","multiple_choice","rating","slider","photo","audio","video","gps","ranking","file"])
@app.post("/studies/{study_id}/edit")
def edit_study(study_id:int,title:str=Form(...),description:str=Form(""),methodology:str=Form(...),status_value:str=Form(...),demographics_schema:str=Form(""),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status"); s.title=title.strip(); s.description=description.strip(); s.methodology=methodology; s.status=status_value; s.demographics_schema_json=json.dumps([x.strip() for x in demographics_schema.splitlines() if x.strip()]); audit(db,u.organisation_id,u.id,"study.updated","study",s.id,s.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/status")
def study_status(study_id:int,status_value:str=Form(...),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); enum_value(status_value,StudyStatus,"study status"); s.status=status_value; db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/studies/{study_id}/activities")
def create_activity(study_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form("long_text"),options:str=Form(""),required:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); allowed={"short_text","long_text","single_choice","multiple_choice","rating","slider","photo","audio","video","gps","ranking","file"}
    if activity_type not in allowed or release_offset_days<0: raise HTTPException(400,"Invalid activity configuration.")
    due=int(due_offset_days) if due_offset_days.strip() else None
    if due is not None and due<release_offset_days: raise HTTPException(400,"Due day cannot be earlier than release day.")
    opts=[x.strip() for x in options.splitlines() if x.strip()]
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"Choice and ranking activities require at least two options.")
    pos=(db.scalar(select(func.max(Activity.position)).where(Activity.study_id==s.id)) or 0)+1; a=Activity(organisation_id=u.organisation_id,study_id=s.id,title=title.strip(),prompt=prompt.strip(),activity_type=activity_type,options_json=json.dumps(opts),position=pos,required=required,release_offset_days=release_offset_days,due_offset_days=due); db.add(a); db.flush(); audit(db,u.organisation_id,u.id,"activity.created","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/activities/{activity_id}/edit")
def edit_activity(activity_id:int,title:str=Form(...),prompt:str=Form(""),activity_type:str=Form(...),options:str=Form(""),required:bool=Form(False),release_offset_days:int=Form(0),due_offset_days:str=Form(""),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==u.organisation_id));
    if not a: raise HTTPException(404)
    require_study_permission(db,u,study(db,a.study_id,u.organisation_id),edit=True)
    due=int(due_offset_days) if due_offset_days.strip() else None; opts=[x.strip() for x in options.splitlines() if x.strip()]
    if due is not None and due<release_offset_days: raise HTTPException(400,"Invalid dates.")
    if activity_type in {"single_choice","multiple_choice","ranking"} and len(opts)<2: raise HTTPException(400,"At least two options required.")
    a.title=title.strip(); a.prompt=prompt.strip(); a.activity_type=activity_type; a.options_json=json.dumps(opts); a.required=required; a.release_offset_days=release_offset_days; a.due_offset_days=due; audit(db,u.organisation_id,u.id,"activity.updated","activity",a.id,a.title); db.commit(); return RedirectResponse(f"/studies/{a.study_id}",303)
@app.post("/activities/{activity_id}/delete")
def delete_activity(activity_id:int,u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.organisation_id==u.organisation_id));
    if not a: raise HTTPException(404)
    require_study_permission(db,u,study(db,a.study_id,u.organisation_id),edit=True)
    sid=a.study_id; db.delete(a); db.commit(); return RedirectResponse(f"/studies/{sid}",303)

@app.get("/participants",response_class=HTMLResponse)
def participants_page(request:Request,q:str="",status_filter:str="",page:int=1,u=Depends(current_user),db:Session=Depends(get_db)):
    stmt=select(Participant).where(Participant.organisation_id==u.organisation_id)
    if q.strip():
        t=f"%{q.strip()}%"; stmt=stmt.where(or_(Participant.name.ilike(t),Participant.reference.ilike(t),Participant.email.ilike(t),Participant.tags.ilike(t)))
    if status_filter: enum_value(status_filter,ParticipantStatus,"participant status"); stmt=stmt.where(Participant.status==status_filter)
    rows,total,pages=paginate(stmt.order_by(Participant.updated_at.desc()),db,page)
    return render(request,"participants.html",user=u,participants=rows,q=q,status_filter=status_filter,statuses=[x.value for x in ParticipantStatus],consent_statuses=[x.value for x in ConsentStatus],page=page,pages=pages,total=total)
@app.post("/participants")
def create_participant(reference:str=Form(...),name:str=Form(...),email:str=Form(""),phone:str=Form(""),status_value:str=Form("prospective"),consent_status:str=Form("pending"),communication_preference:str=Form("email"),tags:str=Form(""),notes:str=Form(""),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    enum_value(status_value,ParticipantStatus,"participant status"); enum_value(consent_status,ConsentStatus,"consent status")
    row=Participant(organisation_id=u.organisation_id,reference=reference.strip().upper(),name=name.strip(),email=email.lower().strip() or None,phone=phone.strip() or None,status=status_value,consent_status=consent_status,communication_preference=communication_preference,tags=tags.strip(),notes=notes.strip(),created_by_id=u.id); db.add(row)
    try: db.flush(); audit(db,u.organisation_id,u.id,"participant.created","participant",row.id,row.reference); db.commit()
    except Exception: db.rollback(); raise HTTPException(400,"Participant reference must be unique.")
    return RedirectResponse(f"/participants/{row.id}",303)
@app.post("/participants/import")
def import_participants(file:UploadFile=File(...),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    data=file.file.read().decode("utf-8-sig"); reader=csv.DictReader(io.StringIO(data)); created=0
    for r in reader:
        ref=(r.get("reference") or "").strip().upper(); name=(r.get("name") or "").strip()
        if not ref or not name or db.scalar(select(Participant.id).where(Participant.organisation_id==u.organisation_id,Participant.reference==ref)): continue
        db.add(Participant(organisation_id=u.organisation_id,reference=ref,name=name,email=(r.get("email") or "").strip().lower() or None,phone=(r.get("phone") or "").strip() or None,status="prospective",consent_status="pending",communication_preference="email",tags=(r.get("tags") or "").strip(),created_by_id=u.id)); created+=1
    audit(db,u.organisation_id,u.id,"participant.bulk_imported","participant","bulk",str(created)); db.commit(); return RedirectResponse("/participants",303)
@app.get("/participants/{participant_id}",response_class=HTMLResponse)
def participant_detail(participant_id:int,request:Request,u=Depends(current_user),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id); ens=db.scalars(select(StudyEnrolment).where(StudyEnrolment.participant_id==p.id,StudyEnrolment.organisation_id==u.organisation_id)).all(); studies={s.id:s for s in db.scalars(select(Study).where(Study.organisation_id==u.organisation_id)).all()}; invs=db.scalars(select(ParticipantInvitation).where(ParticipantInvitation.participant_id==p.id,ParticipantInvitation.organisation_id==u.organisation_id).order_by(ParticipantInvitation.created_at.desc())).all(); responses=db.scalars(select(ActivityResponse).where(ActivityResponse.participant_id==p.id,ActivityResponse.organisation_id==u.organisation_id).order_by(ActivityResponse.updated_at.desc())).all(); messages=db.scalars(select(ParticipantMessage).where(ParticipantMessage.participant_id==p.id,ParticipantMessage.organisation_id==u.organisation_id).order_by(ParticipantMessage.created_at)).all(); return render(request,"participant_detail.html",user=u,participant=p,enrolments=ens,studies=studies,invitations=invs,responses=responses,messages=messages,statuses=[x.value for x in ParticipantStatus],consent_statuses=[x.value for x in ConsentStatus])
@app.post("/participants/{participant_id}/update")
def update_participant(participant_id:int,name:str=Form(None),email:str=Form(None),phone:str=Form(None),status_value:str=Form(...),consent_status:str=Form(...),communication_preference:str=Form(...),tags:str=Form(""),notes:str=Form(""),demographics_json:str=Form("{}"),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id); enum_value(status_value,ParticipantStatus,"participant status"); enum_value(consent_status,ConsentStatus,"consent status")
    if name is not None: p.name=name.strip(); p.email=(email or "").strip().lower() or None; p.phone=(phone or "").strip() or None
    try: json.loads(demographics_json or "{}")
    except: raise HTTPException(400,"Demographics must be valid JSON.")
    p.status=status_value; p.consent_status=consent_status; p.communication_preference=communication_preference; p.tags=tags.strip(); p.notes=notes.strip(); p.demographics_json=demographics_json or "{}"; audit(db,u.organisation_id,u.id,"participant.updated","participant",p.id,p.reference); db.commit(); return RedirectResponse(f"/participants/{p.id}",303)
@app.post("/studies/{study_id}/enrol")
def enrol(study_id:int,participant_id:int=Form(...),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); p=participant(db,participant_id,u.organisation_id)
    if not db.scalar(select(StudyEnrolment).where(StudyEnrolment.study_id==s.id,StudyEnrolment.participant_id==p.id)): db.add(StudyEnrolment(organisation_id=u.organisation_id,study_id=s.id,participant_id=p.id)); audit(db,u.organisation_id,u.id,"participant.enrolled","participant",p.id,s.title); db.commit()
    return RedirectResponse(f"/studies/{s.id}",303)

def send_participant_invite(db,u,s,p):
    raw=new_token(); inv=ParticipantInvitation(organisation_id=u.organisation_id,participant_id=p.id,study_id=s.id,token_hash=token_hash(raw),expires_at=now()+timedelta(days=30),invited_by_id=u.id); db.add(inv); db.flush(); queue_email(db,u.organisation_id,p.email,f"Invitation: {s.title}",f"Join the study: {settings.base_url}/join-study?token={raw}"); p.status="invited"; audit(db,u.organisation_id,u.id,"participant.invited","participant",p.id,s.title); db.commit()
@app.post("/studies/{study_id}/invite/{participant_id}")
def invite_participant(study_id:int,participant_id:int,u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True); p=participant(db,participant_id,u.organisation_id)
    if not p.email: raise HTTPException(400,"Participant requires an email address.")
    active=db.scalar(select(ParticipantInvitation).where(ParticipantInvitation.study_id==s.id,ParticipantInvitation.participant_id==p.id,ParticipantInvitation.accepted_at.is_(None),ParticipantInvitation.revoked_at.is_(None),ParticipantInvitation.expires_at>now()))
    if active: raise HTTPException(400,"A live invitation already exists. Revoke it before resending.")
    send_participant_invite(db,u,s,p); return RedirectResponse(f"/studies/{s.id}",303)
@app.post("/participant-invitations/{invitation_id}/revoke")
def revoke_participant_invite(invitation_id:int,u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    inv=db.scalar(select(ParticipantInvitation).where(ParticipantInvitation.id==invitation_id,ParticipantInvitation.organisation_id==u.organisation_id));
    if not inv: raise HTTPException(404)
    require_study_permission(db,u,study(db,inv.study_id,u.organisation_id),edit=True)
    inv.revoked_at=now(); db.commit(); return RedirectResponse(f"/studies/{inv.study_id}",303)
@app.post("/participant-invitations/{invitation_id}/resend")
def resend_participant_invite(invitation_id:int,u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    inv=db.scalar(select(ParticipantInvitation).where(ParticipantInvitation.id==invitation_id,ParticipantInvitation.organisation_id==u.organisation_id));
    if not inv: raise HTTPException(404)
    require_study_permission(db,u,study(db,inv.study_id,u.organisation_id),edit=True)
    inv.revoked_at=now(); send_participant_invite(db,u,study(db,inv.study_id,u.organisation_id),participant(db,inv.participant_id,u.organisation_id)); return RedirectResponse(f"/studies/{inv.study_id}",303)

@app.get("/join-study",response_class=HTMLResponse)
def join_study(request:Request,token:str="",db:Session=Depends(get_db)):
    inv=db.scalar(select(ParticipantInvitation).where(ParticipantInvitation.token_hash==token_hash(token))); valid=bool(inv and not inv.revoked_at and unexpired(inv.expires_at));
    if valid and not inv.opened_at: inv.opened_at=now(); db.commit()
    s=db.get(Study,inv.study_id) if valid else None; p=db.get(Participant,inv.participant_id) if valid else None
    if valid and inv.accepted_at: return RedirectResponse(f"/participant-portal?token={token}",303)
    return render(request,"join_study.html",token=token,invitation=inv,study=s,participant=p,valid=valid)
@app.post("/join-study")
def accept_study(request:Request,token:str=Form(...),consent:bool=Form(False),db:Session=Depends(get_db)):
    inv=portal_invitation(db,token)
    if not consent: raise HTTPException(400,"Consent is required.")
    p=db.get(Participant,inv.participant_id); inv.accepted_at=inv.accepted_at or now(); p.status="active"; p.consent_status="granted"; audit(db,inv.organisation_id,None,"participant.invitation_accepted","participant",p.id); db.commit(); return RedirectResponse(f"/participant-portal?token={token}",303)
@app.get("/participant-portal",response_class=HTMLResponse)
def participant_portal(request:Request,token:str,db:Session=Depends(get_db)):
    inv=portal_invitation(db,token)
    if not inv.accepted_at: return RedirectResponse(f"/join-study?token={token}",303)
    s=db.get(Study,inv.study_id); p=db.get(Participant,inv.participant_id); acts=db.scalars(select(Activity).where(Activity.study_id==s.id).order_by(Activity.position)).all(); responses={r.activity_id:r for r in db.scalars(select(ActivityResponse).where(ActivityResponse.study_id==s.id,ActivityResponse.participant_id==p.id)).all()}; response_values={}
    for activity_id,response in responses.items():
        try: response_values[activity_id]=json.loads(response.value_json or "{}")
        except json.JSONDecodeError: response_values[activity_id]={}
    msgs=db.scalars(select(ParticipantMessage).where(ParticipantMessage.study_id==s.id,ParticipantMessage.participant_id==p.id,ParticipantMessage.internal_note==False).order_by(ParticipantMessage.created_at)).all(); return render(request,"participant_portal.html",token=token,study=s,participant=p,activities=acts,responses=responses,response_values=response_values,messages=msgs)
@app.post("/participant-portal/activity/{activity_id}")
async def submit_activity(activity_id:int,token:str=Form(...),action:str=Form("submit"),answer:str=Form(""),choices:str=Form(""),upload:UploadFile|None=File(None),db:Session=Depends(get_db)):
    inv=portal_invitation(db,token); a=db.scalar(select(Activity).where(Activity.id==activity_id,Activity.study_id==inv.study_id));
    if not a: raise HTTPException(404)
    r=db.scalar(select(ActivityResponse).where(ActivityResponse.activity_id==a.id,ActivityResponse.participant_id==inv.participant_id))
    if not r: r=ActivityResponse(organisation_id=inv.organisation_id,study_id=inv.study_id,activity_id=a.id,participant_id=inv.participant_id); db.add(r); db.flush()
    choice_list=[x.strip() for x in choices.split("|") if x.strip()]; value={"answer":answer,"choices":choice_list}
    if upload and upload.filename:
        original=Path(upload.filename).name
        extension=Path(original).suffix.lower()
        allowed_extensions={x.strip().lower() for x in settings.allowed_upload_extensions.split(",") if x.strip()}
        if extension not in allowed_extensions:
            raise HTTPException(400,"This file type is not permitted.")
        try:
            stored=storage.save_stream(upload.file,original,settings.max_upload_mb*1024*1024)
        except ValueError as exc:
            raise HTTPException(413,str(exc))
        if stored.provider == "local":
            path=storage.path(stored.key)
            scan_status,scan_detail=scan_file(path)
            if scan_status=="infected":
                storage.delete(stored.key)
                audit(db,inv.organisation_id,None,"evidence.rejected","activity",a.id,scan_detail)
                db.commit()
                raise HTTPException(400,"The uploaded file failed malware screening.")
        else:
            scan_status,scan_detail="pending","Awaiting Microsoft Defender for Storage on-upload scan."
        ev=EvidenceFile(organisation_id=inv.organisation_id,study_id=inv.study_id,activity_id=a.id,participant_id=inv.participant_id,response_id=r.id,original_name=original,stored_name=stored.key,content_type=upload.content_type or "application/octet-stream",size_bytes=stored.size,sha256_hex=stored.sha256_hex,scan_status=scan_status,scan_detail=scan_detail,storage_provider=stored.provider,blob_uri=stored.uri); db.add(ev); db.flush(); value["evidence_id"]=ev.id
    if a.required and action=="submit" and not answer.strip() and not choice_list and not upload: raise HTTPException(400,"A response is required.")
    r.value_json=json.dumps(value); r.status="submitted" if action=="submit" else "draft"; r.submitted_at=now() if action=="submit" else None; audit(db,inv.organisation_id,None,f"activity.{r.status}","activity_response",r.id,str(a.id)); db.commit(); return RedirectResponse(f"/participant-portal?token={token}",303)
@app.post("/participant-portal/message")
def participant_message(token:str=Form(...),body:str=Form(...),db:Session=Depends(get_db)):
    inv=portal_invitation(db,token)
    if not body.strip(): raise HTTPException(400,"Message cannot be empty.")
    db.add(ParticipantMessage(organisation_id=inv.organisation_id,study_id=inv.study_id,participant_id=inv.participant_id,sender_type="participant",body=body.strip())); db.commit(); return RedirectResponse(f"/participant-portal?token={token}#messages",303)
@app.post("/participants/{participant_id}/message")
def researcher_message(participant_id:int,study_id:int=Form(...),body:str=Form(...),internal_note:bool=Form(False),u=Depends(roles("owner","admin","researcher")),db:Session=Depends(get_db)):
    p=participant(db,participant_id,u.organisation_id); s=study(db,study_id,u.organisation_id); require_study_permission(db,u,s,edit=True)
    if not body.strip(): raise HTTPException(400,"Message cannot be empty.")
    db.add(ParticipantMessage(organisation_id=u.organisation_id,study_id=s.id,participant_id=p.id,sender_type="researcher",sender_user_id=u.id,body=body.strip(),internal_note=internal_note)); audit(db,u.organisation_id,u.id,"message.created","participant",p.id,"internal" if internal_note else s.title); db.commit(); return RedirectResponse(f"/participants/{p.id}#messages",303)
@app.get("/evidence/{evidence_id}")
def evidence(evidence_id:int,u=Depends(current_user),db:Session=Depends(get_db)):
    e=db.scalar(select(EvidenceFile).where(EvidenceFile.id==evidence_id,EvidenceFile.organisation_id==u.organisation_id));
    if not e: raise HTTPException(404)
    require_study_permission(db,u,study(db,e.study_id,u.organisation_id))
    if e.storage_provider == "azure_blob":
        latest_status, latest_detail = storage.scan_result(e.stored_name)
        if latest_status != "pending" or e.scan_status == "pending":
            e.scan_status, e.scan_detail = latest_status, latest_detail
            if latest_status in {"clean", "infected", "scan_failed"}: e.scan_completed_at = now()
            db.commit()
        if e.scan_status == "infected": raise HTTPException(423,"Evidence is quarantined because Microsoft Defender detected malware.")
        if settings.defender_require_clean_download and e.scan_status != "clean":
            raise HTTPException(423,"Evidence is awaiting a successful Microsoft Defender scan and cannot yet be downloaded.")
        return RedirectResponse(storage.download_url(e.stored_name,e.original_name,e.content_type,settings.azure_sas_minutes),303)
    if e.scan_status == "infected": raise HTTPException(423,"Evidence is quarantined.")
    path=storage.path(e.stored_name)
    if not path.exists(): raise HTTPException(404,"Stored evidence is unavailable.")
    return FileResponse(path,media_type=e.content_type,filename=e.original_name)

@app.post("/webhooks/defender-storage")
async def defender_storage_webhook(request: Request, db: Session = Depends(get_db)):
    """Receive Event Grid validation and Defender for Storage scan-result events."""
    configured = settings.azure_defender_webhook_secret
    supplied = request.headers.get("x-pcip-webhook-secret") or request.query_params.get("secret")
    if configured and not secrets.compare_digest(configured, supplied or ""):
        raise HTTPException(401, "Invalid webhook secret.")
    payload = await request.json()
    events = payload if isinstance(payload, list) else [payload]
    for event in events:
        event_type = str(event.get("eventType") or event.get("type") or "")
        data = event.get("data") or {}
        if event_type == "Microsoft.EventGrid.SubscriptionValidationEvent":
            return JSONResponse({"validationResponse": data.get("validationCode")})
        blob_uri = str(data.get("blobUri") or data.get("blobURL") or data.get("url") or "")
        raw_result = str(data.get("scanResultType") or data.get("scanResult") or data.get("malwareScanResult") or "")
        if not blob_uri or not raw_result:
            continue
        row = db.scalar(select(EvidenceFile).where(EvidenceFile.blob_uri == blob_uri))
        if not row:
            # Some Event Grid payloads encode the URI; the persisted URI remains the safest lookup.
            continue
        result = raw_result.strip().lower()
        if result == "no threats found": row.scan_status = "clean"
        elif result == "malicious": row.scan_status = "infected"
        elif result in {"error", "not scanned"}: row.scan_status = "scan_failed"
        else: row.scan_status = "pending"
        detail = data.get("scanResultDetails")
        row.scan_detail = json.dumps(detail) if isinstance(detail, (dict, list)) else str(detail or raw_result)
        row.scan_completed_at = now()
        audit(db,row.organisation_id,None,"evidence.defender_scan","evidence_file",row.id,row.scan_status)
    db.commit()
    return {"accepted": True}

@app.post("/studies/{study_id}/access")
def set_study_access(study_id:int,user_id:int=Form(...),permission:str=Form(...),u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    s=study(db,study_id,u.organisation_id)
    target=db.scalar(select(User).where(User.id==user_id,User.organisation_id==u.organisation_id,User.is_active==True))
    if not target: raise HTTPException(404,"Researcher not found.")
    if permission not in {"none","view","edit"}: raise HTTPException(400,"Invalid study permission.")
    row=db.scalar(select(StudyAccess).where(StudyAccess.study_id==s.id,StudyAccess.user_id==target.id))
    if permission=="none":
        if row: db.delete(row)
    elif row:
        row.permission=permission
    else:
        db.add(StudyAccess(organisation_id=u.organisation_id,study_id=s.id,user_id=target.id,permission=permission,created_by_id=u.id))
    audit(db,u.organisation_id,u.id,"study.access_updated","study",s.id,f"{target.email}:{permission}")
    db.commit()
    return RedirectResponse(f"/studies/{s.id}#team-access",303)

@app.get("/researchers",response_class=HTMLResponse)
def researchers(request:Request,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    users=db.scalars(select(User).where(User.organisation_id==u.organisation_id).order_by(User.name)).all(); invs=db.scalars(select(Invitation).where(Invitation.organisation_id==u.organisation_id).order_by(Invitation.created_at.desc())).all(); return render(request,"researchers.html",user=u,users=users,invitations=invs,roles=[x.value for x in Role])
@app.post("/researchers/invite")
def invite_researcher(name:str=Form(...),email:str=Form(...),role:str=Form("researcher"),u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    enum_value(role,Role,"role"); email=email.lower().strip()
    if db.scalar(select(User.id).where(User.organisation_id==u.organisation_id,User.email==email)): raise HTTPException(400,"A user already exists.")
    live=db.scalar(select(Invitation.id).where(Invitation.organisation_id==u.organisation_id,Invitation.email==email,Invitation.accepted_at.is_(None),Invitation.revoked_at.is_(None),Invitation.expires_at>now()))
    if live: raise HTTPException(400,"A live invitation already exists.")
    raw=new_token(); inv=Invitation(organisation_id=u.organisation_id,email=email,name=name.strip(),role=role,token_hash=token_hash(raw),expires_at=now()+timedelta(hours=48),invited_by_id=u.id); db.add(inv); db.flush(); queue_email(db,u.organisation_id,email,"Join PCIP",f"Activate your account: {settings.base_url}/accept-invitation?token={raw}"); db.commit(); return RedirectResponse("/researchers",303)
@app.get("/accept-invitation",response_class=HTMLResponse)
def accept_page(request:Request,token:str="",db:Session=Depends(get_db)):
    inv=db.scalar(select(Invitation).where(Invitation.token_hash==token_hash(token))); return render(request,"accept.html",token=token,invitation=inv,valid=bool(inv and not inv.accepted_at and not inv.revoked_at and unexpired(inv.expires_at)))
@app.post("/accept-invitation")
def accept_invitation(token:str=Form(...),password:str=Form(...),db:Session=Depends(get_db)):
    inv=db.scalar(select(Invitation).where(Invitation.token_hash==token_hash(token)))
    if not inv or inv.accepted_at or inv.revoked_at or not unexpired(inv.expires_at): raise HTTPException(400,"Invitation invalid or expired.")
    if len(password)<10: raise HTTPException(400,"Password must contain at least 10 characters.")
    u=User(organisation_id=inv.organisation_id,name=inv.name,email=inv.email,password_hash=hash_password(password),role=inv.role); db.add(u); db.flush(); inv.accepted_at=now(); db.commit(); r=RedirectResponse("/",303); r.set_cookie("session",encode_session(u.id),httponly=True,samesite="strict",secure=settings.cookie_secure,max_age=43200); return r
@app.post("/invitations/{invitation_id}/revoke")
def revoke_researcher_invite(invitation_id:int,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    inv=db.scalar(select(Invitation).where(Invitation.id==invitation_id,Invitation.organisation_id==u.organisation_id));
    if not inv: raise HTTPException(404)
    inv.revoked_at=now(); db.commit(); return RedirectResponse("/researchers",303)

@app.get("/audit",response_class=HTMLResponse)
def audit_page(request:Request,page:int=1,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    rows,total,pages=paginate(select(AuditEvent).where(AuditEvent.organisation_id==u.organisation_id).order_by(AuditEvent.created_at.desc()),db,page,50); return render(request,"audit.html",user=u,events=rows,page=page,pages=pages,total=total)
@app.get("/outbox",response_class=HTMLResponse)
def outbox(request:Request,page:int=1,u=Depends(roles("owner","admin")),db:Session=Depends(get_db)):
    rows,total,pages=paginate(select(OutboxEmail).where(OutboxEmail.organisation_id==u.organisation_id).order_by(OutboxEmail.created_at.desc()),db,page,50); return render(request,"outbox.html",user=u,rows=rows,smtp_enabled=bool(settings.smtp_host),page=page,pages=pages,total=total)
