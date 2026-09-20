"""Add typed researcher-created analytical relationships."""

import sqlalchemy as sa
from alembic import op

revision="0030"; down_revision="0029"; branch_labels=None; depends_on=None
OBJECTS={"analysis_target":"analysis_targets","code_application":"code_applications","annotation":"research_annotations","memo":"research_memos","code":"research_codes","theme":"research_themes"}


def _drop_guards():
    if op.get_bind().dialect.name=="postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_analytical_relationships_scope ON analytical_relationships"); op.execute("DROP FUNCTION IF EXISTS validate_analytical_relationship_scope()")
    else:
        op.execute("DROP TRIGGER IF EXISTS trg_analytical_relationships_scope_insert"); op.execute("DROP TRIGGER IF EXISTS trg_analytical_relationships_scope_update")


def _create_guards():
    if op.get_bind().dialect.name=="postgresql":
        validations=[]
        for side in ("source","target"):
            for object_type,table in OBJECTS.items():
                validations.append(f"IF NEW.{side}_type='{object_type}' AND NOT EXISTS (SELECT 1 FROM {table} WHERE id=NEW.{side}_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id) THEN RAISE EXCEPTION 'analytical relationship {side} scope'; END IF;")
        op.execute(f"""CREATE FUNCTION validate_analytical_relationship_scope() RETURNS trigger AS $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analytical relationship study scope'; END IF;
        IF NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id) THEN RAISE EXCEPTION 'analytical relationship author scope'; END IF;
        {' '.join(validations)} RETURN NEW; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_analytical_relationships_scope BEFORE INSERT OR UPDATE ON analytical_relationships FOR EACH ROW EXECUTE FUNCTION validate_analytical_relationship_scope();""")
    else:
        for action in ("INSERT","UPDATE"):
            validations=[]
            for side in ("source","target"):
                for object_type,table in OBJECTS.items():
                    validations.append(f"SELECT RAISE(ABORT,'analytical relationship {side} scope') WHERE NEW.{side}_type='{object_type}' AND NOT EXISTS (SELECT 1 FROM {table} WHERE id=NEW.{side}_id AND organisation_id=NEW.organisation_id AND study_id=NEW.study_id);")
            op.execute(f"""CREATE TRIGGER trg_analytical_relationships_scope_{action.lower()} BEFORE {action} ON analytical_relationships BEGIN
            SELECT RAISE(ABORT,'analytical relationship study scope') WHERE NOT EXISTS (SELECT 1 FROM studies WHERE id=NEW.study_id AND organisation_id=NEW.organisation_id);
            SELECT RAISE(ABORT,'analytical relationship author scope') WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=NEW.created_by_id AND organisation_id=NEW.organisation_id);
            {' '.join(validations)} END""")


def upgrade():
    bind=op.get_bind()
    if "analytical_relationships" not in sa.inspect(bind).get_table_names():
        op.create_table("analytical_relationships",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("organisation_id",sa.Integer(),sa.ForeignKey("organisations.id"),nullable=False),sa.Column("study_id",sa.Integer(),sa.ForeignKey("studies.id"),nullable=False),sa.Column("source_type",sa.String(40),nullable=False),sa.Column("source_id",sa.Integer(),nullable=False),sa.Column("relationship_type",sa.String(30),nullable=False),sa.Column("target_type",sa.String(40),nullable=False),sa.Column("target_id",sa.Integer(),nullable=False),sa.Column("rationale",sa.Text(),nullable=False,server_default=""),sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.text("CURRENT_TIMESTAMP")),sa.CheckConstraint("relationship_type IN ('supports','contradicts','explains','relates_to','precedes','follows','refines')",name="ck_analytical_relationship_type"),sa.CheckConstraint("source_type IN ('analysis_target','code_application','annotation','memo','code','theme')",name="ck_analytical_relationship_source_type"),sa.CheckConstraint("target_type IN ('analysis_target','code_application','annotation','memo','code','theme')",name="ck_analytical_relationship_target_type"),sa.CheckConstraint("source_type <> target_type OR source_id <> target_id",name="ck_analytical_relationship_not_self"),sa.UniqueConstraint("organisation_id","study_id","source_type","source_id","relationship_type","target_type","target_id",name="uq_analytical_relationship_assertion"))
        for name,columns in (("source",["organisation_id","study_id","source_type","source_id"]),("target",["organisation_id","study_id","target_type","target_id"]),("organisation_id",["organisation_id"]),("study_id",["study_id"]),("relationship_type",["relationship_type"]),("created_by_id",["created_by_id"])): op.create_index(f"ix_analytical_relationships_{name}","analytical_relationships",columns)
    _drop_guards(); _create_guards()


def downgrade():
    _drop_guards(); op.drop_table("analytical_relationships")
