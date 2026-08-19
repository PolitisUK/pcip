from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityResponse,
    AuditEvent,
    EvidenceConfidenceAssessment,
    EvidenceFile,
    Organisation,
    OrganisationMembership,
    Participant,
    ParticipantInvitation,
    ParticipantMessage,
    Project,
    PublicAuthSession,
    ResearchAnalysisSuggestion,
    ResearchTheme,
    Study,
    StudyAccess,
    StudyEnrolment,
    StudyGovernance,
    StudyMethodologyConfiguration,
    User,
)

RIVERMERE_SLUG = "rivermere-town-council-demo"
EVERYDAY_PROJECT_CODE = "RIV-2035"
EVERYDAY_STUDY_CODE = "RIV2035-ETH"
CHAPEL_PROJECT_CODE = "RIV-CHAPEL"
CHAPEL_STUDY_CODE = "CHAPEL-ETH"
SAFE_ENVIRONMENTS = {"development", "dev"}
ASSET_ROOT = Path(__file__).with_name("assets")


class UnsafeDemoTarget(RuntimeError):
    """Raised before any write when a configured target is not demonstrably local."""


@dataclass
class SeedCounts:
    projects: int = 0
    studies: int = 0
    participants: int = 0
    enrolments: int = 0
    prompts: int = 0
    entries: int = 0
    media: int = 0
    code_assignments: int = 0
    memberships: int = 0
    created_project_codes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "projects": self.projects,
            "studies": self.studies,
            "participants": self.participants,
            "enrolments": self.enrolments,
            "prompts": self.prompts,
            "entries": self.entries,
            "media": self.media,
            "code_assignments": self.code_assignments,
            "memberships": self.memberships,
            "created_project_codes": self.created_project_codes,
        }


def assert_safe_demo_target(
    *, database_url: str, environment: str, storage_backend: str, storage_path: str, repo_root: Path
) -> tuple[Path, Path]:
    """Prove that both database and evidence storage are local to this checkout."""
    if environment.strip().lower() not in SAFE_ENVIRONMENTS:
        raise UnsafeDemoTarget("Rivermere data may only be seeded in an explicit development environment.")
    parsed = urlsplit(database_url.strip())
    if parsed.scheme.lower() != "sqlite" or parsed.netloc:
        raise UnsafeDemoTarget("Rivermere data may only be seeded into a local SQLite database.")
    if storage_backend.strip().lower() != "local":
        raise UnsafeDemoTarget("Rivermere media may only be seeded into local development storage.")

    raw_database_path = database_url.removeprefix("sqlite:///")
    if not raw_database_path or raw_database_path == ":memory:":
        raise UnsafeDemoTarget("Rivermere seeding requires a file-backed local SQLite database.")

    root = repo_root.resolve()
    database_path = (root / raw_database_path).resolve() if not Path(raw_database_path).is_absolute() else Path(raw_database_path).resolve()
    evidence_path = (root / storage_path).resolve() if not Path(storage_path).is_absolute() else Path(storage_path).resolve()
    if root not in database_path.parents or root not in evidence_path.parents:
        raise UnsafeDemoTarget("Database and evidence storage must both resolve inside the current checkout.")
    if database_path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise UnsafeDemoTarget("Configured SQLite target does not have an expected local database suffix.")
    return database_path, evidence_path


EVERYDAY_PARTICIPANTS = [
    ("R2035-01", "Amina Rahman", "Willowbank", "35-44", "NHS receptionist; two school-age children", "housing-association tenant", "walk and bus", "shape each weekday around school runs and care for my mother on Fridays", "Willowbank Primary School, Bus Interchange, Market Square", "practical, attentive to timing and small knock-on effects"),
    ("R2035-02", "Gareth Bell", "Old Market", "65-74", "retired printer; lives alone", "owner-occupier", "walk", "buy a paper after breakfast and sit near Old Market Hall", "Old Market Hall, High Street, Northgate Library", "dry humour; compares current places with remembered uses"),
    ("R2035-03", "Leonie Price", "Station Quarter", "25-34", "hospitality supervisor; shared flat", "private renter", "rail and late bus", "work changing shifts and walk home after the evening economy closes", "Central Station, The Foundry, Mill Street", "direct, sensory, notices who is present after dark"),
    ("R2035-04", "Dev Patel", "Northgate", "45-54", "accountant working hybrid", "owner-occupier", "cycle and rail", "cycle to the station three mornings and work at Northgate Library on others", "Northgate Library, Beacon Road, Central Station", "measured and initially optimistic about incremental improvements"),
    ("R2035-05", "Moira Evans", "Hilltop", "75-84", "retired school cook; widowed", "council tenant", "community bus and lifts", "plan errands around the community bus and call on a neighbour", "Market Square, council office, Meadow Park", "warm, precise about accessibility without defining herself by it"),
    ("R2035-06", "Kai Morgan", "Eastfield", "18-24", "apprentice electrician; lives with family", "family owner-occupied home", "bike and bus", "cross town to a workshop and meet friends at the leisure centre", "Eastfield Leisure Centre, Bus Interchange, Riverside Walk", "brief, energetic, gradually more observant"),
    ("R2035-07", "Ruth Okafor", "Riverside", "35-44", "freelance translator; single parent", "private renter", "walk and bus", "work around nursery hours and take the river path when pushing the buggy", "Riverside Walk, Market Square, Southbank Retail Park", "reflective; connects design details with care work"),
    ("R2035-08", "Peter Walsh", "Westmere", "55-64", "delivery driver", "owner-occupier", "van and walk", "start early, notice loading arrangements, then walk the dog at dusk", "High Street, Meadow Park, Southbank Retail Park", "matter-of-fact; sympathetic to workers and residents"),
    ("R2035-09", "Sofia Lind", "Meadow Park", "25-34", "postgraduate student", "private renter", "walk and cycle", "study in the library and meet a running group twice weekly", "Meadow Park, Northgate Library, Riverside Walk", "curious newcomer who tests local stories against observation"),
    ("R2035-10", "Colin Briggs", "Southbank", "45-54", "warehouse team leader; cares for father", "owner-occupier", "car and bus", "combine shift work with pharmacy and care visits", "Southbank Retail Park, Beacon Road, council office", "impatient with vague communication but willing to revise his view"),
    ("R2035-11", "Nadia Hussein", "Old Market", "35-44", "independent café owner", "rents flat above business", "walk", "open before eight and watch footfall change across the day", "High Street, Old Market Hall, Market Square", "socially connected; distinguishes rumour from what she witnessed"),
    ("R2035-12", "Tom Rees", "Northgate", "25-34", "remote software tester", "private renter", "walk and occasional taxi", "work from home and use the library to avoid isolation", "Northgate Library, The Foundry, Mill Street", "digitally confident but alert to exclusion created by online-only systems"),
    ("R2035-13", "Jeanette Cole", "Willowbank", "55-64", "teaching assistant", "housing-association tenant", "walk and bus", "walk to school, shop locally, and help at the community centre", "Willowbank Community Centre, Primary School, Market Square", "relational voice; notices informal care networks"),
    ("R2035-14", "Bilal Khan", "Eastfield", "35-44", "self-employed taxi driver", "owner-occupier", "car", "see the town between fares and wait near the station rank", "Central Station, Eastfield Leisure Centre, High Street", "observational, pragmatic about traffic trade-offs"),
    ("R2035-15", "Eleanor Shaw", "Riverside", "65-74", "retired solicitor", "owner-occupier", "walk with stick and bus", "walk a fixed river circuit and attend a reading group", "Riverside Walk, Northgate Library, Market Square", "careful about evidence and the difference between inconvenience and exclusion"),
    ("R2035-16", "Jayden Clarke", "Southbank", "18-24", "college student; part-time retail worker", "family private-rented home", "bus and walk", "travel between college, retail shifts and football practice", "Bus Interchange, Southbank Retail Park, Meadow Park", "informal, candid, notices spaces young people are moved on from"),
    ("R2035-17", "Helen Wu", "Station Quarter", "45-54", "architectural technician", "leaseholder", "rail and walk", "commute twice weekly and sketch changing street edges", "Station Road, The Foundry, Market Square", "visual and spatial; hopeful about regeneration but records its costs"),
    ("R2035-18", "Martin Doyle", "Hilltop", "55-64", "unemployed after factory closure", "council tenant", "bus", "use the job club, food co-op and low-cost cafés", "Community Centre, High Street, Bus Interchange", "plain-spoken; sees price and waiting time as design constraints"),
    ("R2035-19", "Priya Sen", "Westmere", "35-44", "occupational therapist; wheelchair user", "owner-occupier", "adapted car and wheel", "visit clients, shop between appointments and scout accessible routes", "disabled bays, Market Square, Riverside Walk", "specific and comparative about access; rejects token solutions"),
    ("R2035-20", "Owen Matthews", "Meadow Park", "45-54", "grounds-maintenance contractor", "private renter", "van and walk", "work outdoors and coach a junior team at weekends", "Meadow Park, Eastfield Leisure Centre, Riverside Walk", "notices maintenance labour and seasonal change"),
]


CHAPEL_PARTICIPANTS = [
    ("CHAP-01", "Marian Holt", "Chapel Lane", "65-74", "retired nurse, directly opposite the yard", "concern → active reporter → fatigue → stopped reporting", "keeps times carefully and notices the street from her front room"),
    ("CHAP-02", "Darren Yates", "Mill Street", "35-44", "night-shift baker sleeping during mornings", "sleep disruption → repeated reports → angry disengagement", "blunt about lost sleep but distinguishes noise he can live with"),
    ("CHAP-03", "Lucy Adeyemi", "Chapel Lane", "35-44", "parent walking two children to Willowbank Primary", "safety concern → collective reporter → route adaptation", "situates observations in the school run and children's reactions"),
    ("CHAP-04", "Neville Grant", "Chapel Lane", "75-84", "retired mechanic; remembers the old timber store", "sceptical → accepts intensification → remains moderate", "compares machinery knowledge with neighbours' interpretations"),
    ("CHAP-05", "Farah Mahmood", "Beacon Road", "25-34", "private tenant and pharmacy assistant", "quiet concern → evidence sharing → reluctant non-reporter", "worries about being seen as troublesome and relies on trusted neighbours"),
    ("CHAP-06", "Rob Mercer", "Chapel Lane", "45-54", "owner of a fictional corner shop", "minimises complaints → observes obstruction → conditional concern", "sees customers, workers and residents and resists a simple villain story"),
    ("CHAP-07", "Tessa Green", "Mill Street", "55-64", "residents' association secretary", "organiser → informal case coordinator → exhausted organiser", "tracks references and carries other residents' reporting labour"),
    ("CHAP-08", "Imogen Reed", "Chapel Lane", "25-34", "new homeowner and secondary teacher", "unfamiliar → hopeful reporter → disappointed but still engaged", "asks what is known rather than inheriting every local rumour"),
    ("CHAP-09", "Marcus Flynn", "Riverside", "35-44", "cycle courier using Chapel Lane as a cut-through", "near miss → occasional reporter → route avoidance", "focuses on vehicle movement and does not experience the domestic noise"),
    ("CHAP-10", "Shazia Cooper", "Chapel Lane", "45-54", "home-based seamstress with asthma", "dust observation → systematic logger → window-closing adaptation", "careful not to claim medical causation; records when dust and symptoms coincide"),
    ("CHAP-11", "Alan Pritchard", "Beacon Road", "55-64", "planning technician in a different fictional authority", "supports investigation → explains complexity → criticises opacity", "separates possible legal work from the absence of resident communication"),
    ("CHAP-12", "Bethany Snow", "Chapel Lane", "18-24", "student living with parents", "photo contributor → form fatigue → silent witness", "initially documents everything on her phone then stops uploading"),
    ("CHAP-13", "Kenji Morris", "Mill Street", "35-44", "care worker and renter", "non-reporter → daily adaptation → loss of trust", "rarely files forms but changes parking and sleep arrangements"),
    ("CHAP-14", "Rose Bennett", "Chapel Lane", "65-74", "volunteer gardener", "patient observer → conditional trust → asks for explanation", "notices seasonal persistence and remains sympathetic to constrained staff"),
]


EVERYDAY_PROMPTS = [
    ("Week 1 · An ordinary day", "Take us through an ordinary day in Rivermere. Where do you go, what do you notice, and who do you encounter?", "long_text"),
    ("Week 2 · An unnoticed place", "Show us a place you use without really thinking about it. Why is it part of your routine?", "long_text"),
    ("Week 3 · Something that helps", "Photograph something that makes everyday life easier.", "photo"),
    ("Week 4 · A learned workaround", "Photograph something you have learned to work around.", "photo"),
    ("Week 5 · A recent journey", "Tell us about a recent journey through Rivermere.", "long_text"),
    ("Week 6 · Ten minutes in place", "Spend ten minutes somewhere you use regularly and describe what happens around you.", "long_text"),
    ("Week 7 · A local conversation", "Tell us about a conversation you had about Rivermere this week.", "long_text"),
    ("Week 8 · A place that changed", "Show us a place that has changed.", "photo"),
    ("Week 9 · Belonging", "Tell us about somewhere you feel you belong.", "long_text"),
    ("Week 10 · Not designed for me", "Tell us about somewhere that feels as though it is not designed for you.", "long_text"),
    ("Week 11 · Signs of the council", "What signs do you notice that the council is present in everyday life?", "long_text"),
    ("Week 12 · Signs of neglect", "What signs do you notice when something is not being maintained?", "long_text"),
    ("Week 13 · Doing things differently", "Tell us about something you now do differently because of a problem in the town.", "long_text"),
    ("Week 14 · New awareness", "What have you become more aware of since taking part?", "long_text"),
    ("Week 15 · Another resident's view", "Has another resident made you see an issue differently?", "long_text"),
    ("Week 16 · What a visitor would miss", "What would someone miss about Rivermere if they only visited for one day?", "long_text"),
]


CHAPEL_PROMPTS = [
    ("Month 1 · What changed?", "Record the first moment you noticed something different at the Chapel Lane yard. What made it stand out?", "long_text"),
    ("Month 2 · Compare notes", "Describe a conversation in which neighbours compared what they had seen or heard.", "long_text"),
    ("Month 3 · Told to report it", "How did you come to understand what residents were expected to record or report?", "long_text"),
    ("Month 4 · Active evidence", "Log one incident in context: time, place, activity, who was present and what you did next.", "photo"),
    ("Month 5 · Acknowledgement and waiting", "What response or acknowledgement followed, and what—if anything—was visible on the street?", "long_text"),
    ("Month 6 · Repetition", "Describe something you have now recorded more than once. How has repetition changed its meaning?", "long_text"),
    ("Month 7 · Evidence burden", "What work does reporting now require from you or your neighbours?", "long_text"),
    ("Month 8 · Frustration and uncertainty", "What do you think may be happening inside the process, and what remains unknown?", "long_text"),
    ("Month 9 · Reporting fatigue", "Tell us about an incident you noticed but nearly did not—or did not—report.", "long_text"),
    ("Month 10 · Stopped reporting", "Do you still report incidents? Explain what changed in your behaviour and what remains on Chapel Lane.", "long_text"),
    ("Month 11 · Normalisation", "Show how you now organise an ordinary day around the unresolved issue.", "photo"),
    ("Month 12 · Looking back", "Has the issue changed, or mainly your response to it? What would rebuild confidence?", "long_text"),
]


EVERYDAY_SCENES = [
    ("a wet Monday school-and-work journey", "the Bus Interchange display held at six minutes and then removed the service", "three strangers compared the delay with the previous morning", "Mobility > Bus reliability|Everyday routines > Workarounds|Council in everyday life > Trust"),
    ("the small paved edge beside Old Market Hall", "people used the low wall as a seat while the formal benches stood inside the works barrier", "a shop worker brought an older customer a chair", "Place and belonging > Familiarity|Public space > Seating|Community > Informal support"),
    ("a recently repaired dropped kerb near Market Square", "a buggy, a trolley and a wheelchair could all cross without entering the traffic", "two people noticed the repair only when the crossing worked smoothly", "Mobility > Accessibility|Council in everyday life > Visible council action|Everyday routines > Caring"),
    ("the Beacon Road crossing at the evening peak", "the short signal phase left slower walkers waiting on the central island", "regular users timed their approach rather than trust one green phase", "Mobility > Walking|Inequality and inclusion > Disability access|Everyday routines > Workarounds"),
    ("a journey between Willowbank and the station", "roadworks changed the bus stop location without a sign at the usual shelter", "passengers passed the news down the queue from someone who had asked a driver", "Mobility > Journey planning|Council in everyday life > Communication|Community > Local networks"),
    ("ten minutes beside the Meadow Park play area", "dog walkers, carers and teenagers shared the same edge without speaking until a loose gate banged", "a grandparent wedged it safely and another visitor reported it", "Public space > Informal social life|Environment > Maintenance|Community > Intergenerational contact"),
    ("a conversation at a fictional independent café", "people repeated a rumour that High Street rents were rising, although nobody knew the source", "the proprietor separated what she had heard from two actual notices", "Community > Local networks|Town centre > Independent business|Council in everyday life > Distrust"),
    ("the changing frontage of The Foundry", "new lighting made the route feel clearer while barriers narrowed the pavement", "a commuter welcomed the investment and a mobility-scooter user called it another temporary exclusion", "Town centre > Regeneration|Town centre > Construction disruption|Futures > Trade-offs"),
    ("a regular table at Northgate Library", "staff recognised who needed help with forms and who mainly came for company", "a volunteer quietly moved chairs to keep the route open", "Place and belonging > Belonging|Community > Community venues|Inequality and inclusion > Digital exclusion"),
    ("Southbank Retail Park without a car", "the pedestrian route ended behind a loading bay and added two crossings", "a parent and a shift worker described different risks on the same path", "Mobility > Walking|Inequality and inclusion > Spatial inequality|Public space > Safety"),
    ("freshly cut verges and a repaired riverside bin", "the maintenance crew's short visit changed how cared-for the whole stretch felt", "walkers thanked the crew but disagreed about whether this was routine or exceptional", "Environment > Maintenance|Council in everyday life > Visible council action|Place and belonging > Pride"),
    ("the shuttered unit beside a busy grocer", "wind gathered packaging in the recessed doorway every afternoon", "nearby traders swept it because waiting for ownership to be resolved left their frontage affected", "Town centre > Empty shops|Environment > Litter|Everyday routines > Workarounds"),
    ("a revised morning routine", "leaving twenty minutes earlier reduced missed connections but removed an unhurried family or neighbourly moment", "the adaptation made the service problem less visible to anyone counting complaints", "Everyday routines > Workarounds|Mobility > Travel adaptation|Council in everyday life > Invisible council"),
    ("the same route after fourteen weeks of observation", "small design choices now stood out: seat height, shelter position, kerbs and places to pause", "what first looked like personal preference now appeared patterned across several lives", "Inequality and inclusion > Unequal service experience|Mobility > Accessibility|Place and belonging > Familiarity"),
    ("a discussion with another participant at the community centre", "a confident cyclist explained why a painted lane felt sufficient to him while a parent described avoiding it", "neither account cancelled the other; the difference was exposure and responsibility", "Mobility > Cycling|Futures > Trade-offs|Community > Intergenerational contact"),
    ("an ordinary Saturday across Rivermere", "the town worked through remembered shortcuts, familiar staff, borrowed chairs and warnings about delayed buses", "a one-day visitor would see facilities but miss the relationships and adaptations holding them together", "Place and belonging > Local identity|Community > Informal support|Futures > Desired change"),
]


CHAPEL_SCENES = [
    ("something_has_changed", "a larger vehicle arrived before seven and reversed where only small vans used to turn", "Nobody was certain whether this was a breach or a temporary delivery, so the first note was a question rather than an accusation.", "Observing change > Vehicle movement|Interpreting enforcement > Uncertainty"),
    ("neighbours_compare_notes", "neighbours compared window photographs, remembered delivery times and disagreed about how unusual the week had been", "The conversation created a shared account, but one resident thought the loudest claims exceeded what the photographs showed.", "Local knowledge > Comparing observations|Community dynamics > Disagreement"),
    ("told_to_report", "the residents' group repeated fictional Rivermere advice to keep dates, photographs and individual reports so a pattern could be assessed", "Reporting still felt like a route to action, and completing the form was described as a civic responsibility rather than a burden.", "Reporting > Told to report it|Reporting > Keeping records|Trust > Initial faith"),
    ("active_reporting", "a reversing alarm sounded at 06:18 while wrapped materials stood above the screening and a fictional report CL-24-0417 was submitted", "The photograph, time and direction of travel were logged; neighbours compared acknowledgement numbers and waited for an update.", "Observing change > Changed hours|Reporting > Photographic evidence|Reporting > Reference numbers|Evidence burden > Resident monitoring"),
    ("acknowledgement_and_waiting", "an automated acknowledgement arrived promptly but the same floodlight was visible from the bedroom that evening", "Residents began distinguishing a response from an outcome while allowing that investigation or negotiation might be happening out of view.", "Council response > Acknowledgement|Council response > Lack of visible action|Interpreting enforcement > Understanding procedural complexity"),
    ("repetition_without_resolution", "another Saturday delivery resembled four earlier entries already sent with dates and photographs", "The incident no longer felt exceptional; the unanswered question became why residents were generating the same evidence again.", "Reporting fatigue > Repetition|Evidence burden > Repeated documentation|Persistence of the issue > Problem remains"),
    ("evidence_burden", "the spreadsheet, portal checks, photograph labels and neighbour messages took most of an evening", "Active residents had become unpaid monitors, and less confident neighbours increasingly forwarded material to one informal coordinator.", "Evidence burden > Administrative labour|Evidence burden > Time burden|Community dynamics > Reliance on active neighbours"),
    ("frustration", "another request asked for dates that appeared in earlier reports, while no resident could see what stage the fictional case had reached", "Some blamed delay; others defended evidential and legal constraints. Almost everyone wanted a plain explanation of what happened next.", "Council response > Request for evidence|Council response > Process opacity|Trust > Conditional trust"),
    ("reporting_fatigue", "the reversing alarm sounded again, but the phone stayed on the kitchen table and no new form was opened", "The activity remained noticeable; what changed was the willingness to turn an ordinary disruption into another administrative record.", "Reporting fatigue > Reduced reporting|Reporting fatigue > Doubt about usefulness|Disengagement > Learned non-reporting|Persistence of the issue > Silent persistence"),
    ("stopped_reporting", "lorries and early activity were still observed, but several residents had stopped filing reports because they perceived that nothing happened", "They worried that a quieter portal might be read as improvement even though only the reporting behaviour had declined.", "Disengagement > Stopped reporting|Disengagement > Loss of trust|Persistence of the issue > Continued impact without reports"),
    ("normalisation_and_adaptation", "windows stayed shut, visitors were warned where not to park and the school route shifted to Beacon Road", "These adaptations reduced daily confrontation without resolving the underlying activity; inconvenience had been absorbed into routine.", "Experiencing the issue > Adaptation|Persistence of the issue > Normalisation|Persistence of the issue > Problem remains"),
    ("retrospective_reflection", "looking back, the yard appeared no quieter than at the start, while photographs, group messages and reports had become much less frequent", "Residents differentiated possible unseen enforcement work from their lived experience of apparent non-resolution and asked for honest, periodic communication.", "Interpreting enforcement > Desire for explanation|Disengagement > Silent persistence|Trust > Loss of confidence|Persistence of the issue > Problem remains"),
]


EVERYDAY_PERSPECTIVES = {
    "R2035-01": "The delay came out of the calm part of the school handover; breakfast club solved the timetable but cost money and time with the children.",
    "R2035-02": "I compared the detail with how this corner worked when the market hall still drew a morning queue, without assuming older automatically means better.",
    "R2035-03": "My test is whether the place still works after a late shift, when help, open doors and other people are much thinner on the ground.",
    "R2035-04": "I first treated it as a small operational snag; seeing the same friction on several journeys made that explanation less comfortable.",
    "R2035-05": "A place to pause turns a possible outing into one I can manage myself, so a missing seat is not a decorative issue to me.",
    "R2035-06": "I would once have ridden straight past; doing the diary made me stop long enough to see who waited and who gave up.",
    "R2035-07": "With a buggy, every extra crossing and closed door becomes a negotiation involving sleep, weather and whether someone offers a hand.",
    "R2035-08": "I know deliveries cannot be made invisibly, so I watched for the difference between necessary work and avoidable obstruction.",
    "R2035-09": "As a newcomer I checked the local story against three separate visits before deciding that the pattern was more than nostalgia.",
    "R2035-10": "The added minutes mattered because I was fitting the trip between a shift and my father's prescription, not because I expected everything instantly.",
    "R2035-11": "From the café doorway, footfall is not an abstract count: I recognise school groups, carers, regulars and the gap when a bus fails to arrive.",
    "R2035-12": "The online answer was quick for me, but I watched two library users need staff help before the same answer became usable.",
    "R2035-13": "What looked like a facility problem became a relationship story once neighbours started lending chairs, directions and lifts.",
    "R2035-14": "Between fares I see the same junction from a driver's queue, a passenger's deadline and the pavement where someone is waiting to cross.",
    "R2035-15": "I separated a minor inconvenience from a barrier by asking whether I could complete the journey safely without relying on a stranger.",
    "R2035-16": "Young people were present in the space but rarely treated as legitimate users unless we were buying something or moving through.",
    "R2035-17": "The new design read well on a plan; at walking pace I noticed temporary edges and pinch points that the finished image leaves out.",
    "R2035-18": "A five-pound alternative or a twenty-minute wait is not small when the week's journeys are being rationed against other costs.",
    "R2035-19": "I compared the advertised accessible route with the route I could actually wheel without reversing into traffic or asking for objects to be moved.",
    "R2035-20": "Maintenance was visible as labour: a short repair depended on people, tools, timing and the public noticing before the result faded into normality.",
}


CHAPEL_PERSPECTIVES = {
    "CHAP-01": "From my front room I could compare the clock with the movement outside; later I stopped reaching for the notebook even though the view did not change.",
    "CHAP-02": "Because I sleep after a night shift, the same morning alarm had a different consequence for me than for neighbours already awake.",
    "CHAP-03": "On the school run I watched the pavement and the children's hesitation, then moved the route rather than test the same squeeze each morning.",
    "CHAP-04": "My experience with machinery made me question exaggerated descriptions, but it also made the change in vehicle scale difficult to dismiss.",
    "CHAP-05": "I shared evidence privately before I felt able to attach my name to a report, and later relied on neighbours to submit what I still noticed.",
    "CHAP-06": "Customers included site workers and worried residents; the obstruction, rather than the existence of a business, was what altered my view.",
    "CHAP-07": "The reference list grew into a second unpaid job as neighbours forwarded photographs and asked me whether anybody had replied.",
    "CHAP-08": "I arrived without the history, so early acknowledgements felt reassuring; disappointment developed from what I then observed myself.",
    "CHAP-09": "I did not hear the night noise from home, but a close pass changed my cycling route and made the vehicle pattern personally relevant.",
    "CHAP-10": "I logged dust and symptoms alongside weather without claiming one caused the other, then began keeping the workroom window shut by default.",
    "CHAP-11": "I understood that enforcement can be slow and legally constrained; that knowledge made the absence of plain communication less, not more, defensible.",
    "CHAP-12": "At first every photograph felt useful; by spring the camera roll held incidents that I could not face labelling and uploading again.",
    "CHAP-13": "I almost never used the portal, but I changed parking, sleep and visitor arrangements, so low reporting did not mean low impact.",
    "CHAP-14": "I measured persistence through seasons in the garden and remained patient, provided patience did not have to mean silence from the process.",
}


EVERYDAY_MEMOS = [
    "Everyday adaptations hide service failure", "The importance of familiar public spaces", "Maintenance as an indicator of institutional care", "Different meanings of accessibility", "Regeneration is experienced as hope and inconvenience", "Local knowledge travels through informal conversation", "Repeated minor frustrations accumulate into distrust", "Green space operates as social infrastructure", "Civic trust is shaped by mundane encounters", "Different neighbourhoods experience Rivermere as different towns", "Digital convenience can redistribute rather than remove effort", "A visible repair can change interpretation beyond the repaired object",
]

CHAPEL_MEMOS = [
    "Reporting as unpaid civic labour", "The difference between acknowledgement and action", "Residents initially understand reporting as a route to resolution", "Repeated requests for evidence shift responsibility onto residents", "Declining reports can conceal continuing harm", "Reporting fatigue should not be interpreted as resolution", "Residents adapt to unresolved environmental problems", "Process opacity contributes to distrust", "Active residents become informal case coordinators", "Disengagement spreads socially", "Non-reporting becomes a learned behaviour", "Institutional trust is damaged beyond the original planning issue", "Residents distinguish legal complexity from poor communication", "The unresolved issue becomes normalised", "Silence is not satisfaction",
]


def _now(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _profile_json(row: tuple[str, ...], *, chapel: bool = False) -> str:
    if chapel:
        _, _, neighbourhood, age, relationship, trajectory, voice = row
        value = {
            "fictional_demo": True, "age_range": age, "neighbourhood": neighbourhood,
            "relationship_to_place": relationship, "trajectory": trajectory, "voice_note": voice,
        }
    else:
        _, _, neighbourhood, age, household, housing, transport, routine, places, voice = row
        value = {
            "fictional_demo": True, "age_range": age, "neighbourhood": neighbourhood,
            "household_and_work": household, "housing_tenure": housing, "transport_habits": transport,
            "routine_and_constraints": routine, "recurring_places": places.split(", "), "voice_note": voice,
        }
    return json.dumps(value, ensure_ascii=False)


def _everyday_text(profile: tuple[str, ...], week: int) -> tuple[str, str, str, list[str]]:
    reference, name, neighbourhood, _, _, _, transport, routine, places, _ = profile
    place, observation, encounter, code_string = EVERYDAY_SCENES[week]
    first_name = name.split()[0]
    observation_lead = ["The detail I wrote down was that", "What stayed with me was that", "At the time, I noticed that"][int(reference[-2:]) % 3]
    change = (
        "At the beginning I would have called it a one-off. Repetition has made me plan around it, which is convenient for everyone except me."
        if week >= 12
        else "I wrote it down because the practical detail mattered more than a general rating of the town."
    )
    text = (
        f"{first_name}'s field entry — {neighbourhood}. My usual pattern is that I {routine}. "
        f"This week I paid attention to {place}. {observation_lead} {observation}. "
        f"In the same period, {encounter}. {EVERYDAY_PERSPECTIVES[reference]} "
        f"I normally travel by {transport}, so the same place can feel different when the timing, weather or people with me change. "
        f"{change} My recurring Rivermere places are {places}; seeing them repeatedly has made small changes easier to notice. "
    )
    entry_type = "photo_elicitation" if EVERYDAY_PROMPTS[week][2] == "photo" else ("place_observation" if week in {5, 8, 10, 11} else "longitudinal_diary")
    return text, entry_type, place, code_string.split("|")


def _chapel_text(profile: tuple[str, ...], month: int) -> tuple[str, str, str, list[str]]:
    reference, name, _, _, relationship, trajectory, _ = profile
    phase, observation, interpretation, code_string = CHAPEL_SCENES[month]
    first_name = name.split()[0]
    interpretive_position = {
        "CHAP-04": "I still think some neighbours treat every engine as proof, but the hours and scale have plainly changed.",
        "CHAP-06": "The yard supports ordinary livelihoods, and not every delivery is unreasonable; the blocked pavement is harder to dismiss.",
        "CHAP-11": "A slow process is not proof of inactivity, yet procedural complexity does not explain months without a useful resident update.",
        "CHAP-14": "I remain willing to believe staff are working within constraints, but patience needs information to survive.",
    }.get(reference, "What I can evidence is the lived pattern; I cannot see or claim what is happening inside the fictional enforcement process.")
    text = (
        f"{first_name}'s Chapel Lane field entry — {phase.replace('_', ' ')}. I relate to the lane as {relationship}. "
        f"On this occasion, {observation}. {interpretation} {CHAPEL_PERSPECTIVES[reference]} {interpretive_position} "
        f"My longer trajectory is {trajectory}. The important change is not always at the yard: it is also in what I now record, discuss, avoid or leave unreported. "
    )
    entry_type = "photo_evidence" if CHAPEL_PROMPTS[month][2] == "photo" else ("incident_account" if month < 6 else "longitudinal_reflection")
    return text, entry_type, "14–18 Chapel Lane, Rivermere (fictional)", code_string.split("|")


def _get_or_create_project(db: Session, organisation_id: int, user_id: int, *, code: str, title: str, description: str, counts: SeedCounts) -> Project:
    row = db.scalar(select(Project).where(Project.organisation_id == organisation_id, Project.code == code))
    if row:
        return row
    row = Project(organisation_id=organisation_id, created_by_id=user_id, code=code, title=title, description=description, status="live")
    db.add(row); db.flush(); counts.projects += 1; counts.created_project_codes.append(code)
    return row


def _get_or_create_study(db: Session, organisation_id: int, user_id: int, project: Project, *, code: str, title: str, description: str, start: datetime, end: datetime, counts: SeedCounts) -> Study:
    row = db.scalar(select(Study).where(Study.organisation_id == organisation_id, Study.code == code))
    if row:
        return row
    demographics = ["age_range", "neighbourhood", "housing_tenure", "transport_habits", "routine_and_constraints", "recurring_places", "trajectory"]
    row = Study(
        organisation_id=organisation_id, project_id=project.id, created_by_id=user_id, code=code,
        title=title, description=description, methodology="ethnography_and_participant_observation",
        # These are completed retrospective demonstrations. Keeping them closed avoids
        # bypassing the platform's controller-owned governance gate for live recruitment.
        status="closed", start_at=start, end_at=end, demographics_schema_json=json.dumps(demographics),
        created_at=start - timedelta(days=28), updated_at=end,
    )
    db.add(row); db.flush(); counts.studies += 1
    configuration = StudyMethodologyConfiguration(
        organisation_id=organisation_id, study_id=row.id, primary_methodology_id="M03",
        methodology_variant="focused longitudinal, multi-sited community ethnography",
        secondary_methodologies_json=json.dumps(["longitudinal diary", "photo elicitation", "place-based observation"]),
        research_questions=("How are everyday civic conditions experienced through routine, place, relationships and adaptation over time? "
                            "What contradictory interpretations and negative cases qualify emerging patterns?"),
        protocol_reference="RIVERMERE-DEMO-PROTOCOL (fictional demonstration only)", protocol_version="1.0-demo",
        sampling_approach="Purposive maximum-variation sample across neighbourhood, routine, mobility, tenure, caring and relationship to place.",
        data_collection_plan="Repeated diary, incident, journey, place-observation and photo-elicitation contributions; progressive focusing with negative-case retention.",
        ai_enabled=False, allowed_ai_tasks_json="[]", human_review_required=True, library_version="1.0.0",
        researcher_notes="Fictional demonstration dataset. Interpret accounts as situated evidence, not population prevalence or verified legal fact.",
        researcher_confirmed_by_id=user_id, researcher_confirmed_at=start - timedelta(days=21),
    )
    db.add(configuration)
    return row


def _participants(db: Session, organisation_id: int, user_id: int, rows: list[tuple[str, ...]], study: Study, counts: SeedCounts, *, chapel: bool) -> list[Participant]:
    result = []
    for row in rows:
        reference, name = row[:2]
        participant = db.scalar(select(Participant).where(Participant.organisation_id == organisation_id, Participant.reference == reference))
        if not participant:
            participant = Participant(
                organisation_id=organisation_id, reference=reference, name=name,
                email=f"{reference.lower()}@participants.rivermere.demo.invalid", status="completed",
                consent_status="granted", communication_preference="none", tags="fictional-demo,ethnography," + ("chapel-lane" if chapel else "rivermere-2035"),
                demographics_json=_profile_json(row, chapel=chapel),
                notes="Entirely fictional participant. Biography, identity and contributions exist only for product demonstration.",
                created_by_id=user_id, created_at=study.start_at - timedelta(days=14), updated_at=study.end_at,
            )
            db.add(participant); db.flush(); counts.participants += 1
        enrolment = db.scalar(select(StudyEnrolment).where(StudyEnrolment.study_id == study.id, StudyEnrolment.participant_id == participant.id))
        if not enrolment:
            db.add(StudyEnrolment(organisation_id=organisation_id, study_id=study.id, participant_id=participant.id, status="completed", enrolled_at=study.start_at - timedelta(days=7)))
            counts.enrolments += 1
        result.append(participant)
    return result


def _activities(db: Session, organisation_id: int, study: Study, prompts: list[tuple[str, str, str]], spacing_days: int, counts: SeedCounts) -> list[Activity]:
    rows = []
    for index, (title, prompt, activity_type) in enumerate(prompts):
        activity = db.scalar(select(Activity).where(Activity.organisation_id == organisation_id, Activity.study_id == study.id, Activity.position == index + 1))
        if not activity:
            activity = Activity(
                organisation_id=organisation_id, study_id=study.id, title=title, prompt=prompt,
                activity_type=activity_type, options_json="[]", position=index + 1, required=False,
                release_offset_days=index * spacing_days, due_offset_days=index * spacing_days + spacing_days - 1,
                created_at=study.start_at - timedelta(days=14),
            )
            db.add(activity); db.flush(); counts.prompts += 1
        rows.append(activity)
    return rows


def _response(db: Session, organisation_id: int, study: Study, activity: Activity, participant: Participant, *, text: str, entry_type: str, place: str, codes: list[str], observed_at: datetime, phase: str, counts: SeedCounts) -> ActivityResponse:
    row = db.scalar(select(ActivityResponse).where(ActivityResponse.activity_id == activity.id, ActivityResponse.participant_id == participant.id))
    if row:
        return row
    value = {
        "text": text, "entry_type": entry_type, "observed_at": observed_at.isoformat(), "place": place,
        "researcher_codes": codes, "trajectory_stage": phase, "fictional_demo": True,
        "analysis_note": "Codes are deterministic researcher-demo metadata in the response payload; no AI job is claimed.",
    }
    row = ActivityResponse(
        organisation_id=organisation_id, study_id=study.id, activity_id=activity.id,
        participant_id=participant.id, value_json=json.dumps(value, ensure_ascii=False), status="submitted",
        submitted_at=observed_at + timedelta(hours=2), updated_at=observed_at + timedelta(hours=2),
    )
    db.add(row); db.flush(); counts.entries += 1; counts.code_assignments += len(codes)
    return row


def _save_evidence(db: Session, storage, *, organisation_id: int, study: Study, response: ActivityResponse, original_name: str, stream: BinaryIO, content_type: str, counts: SeedCounts) -> None:
    existing = db.scalar(select(EvidenceFile).where(EvidenceFile.organisation_id == organisation_id, EvidenceFile.study_id == study.id, EvidenceFile.response_id == response.id, EvidenceFile.original_name == original_name))
    if existing:
        return
    stored = storage.save_stream(stream, original_name, 25 * 1024 * 1024)
    db.add(EvidenceFile(
        organisation_id=organisation_id, study_id=study.id, activity_id=response.activity_id,
        participant_id=response.participant_id, response_id=response.id, original_name=original_name,
        stored_name=stored.key, content_type=content_type, size_bytes=stored.size, sha256_hex=stored.sha256_hex,
        scan_status="clean", scan_detail="Bundled or generated fictional development-demo evidence; no external upload.",
        storage_provider=stored.provider, blob_uri=stored.uri, scan_completed_at=response.submitted_at,
        created_at=response.submitted_at,
    ))
    counts.media += 1


def _artifact_bytes(*, project: str, response: ActivityResponse, index: int, caption: str) -> bytes:
    payload = {
        "classification": "FICTIONAL DEMONSTRATION MATERIAL — NOT A REAL COUNCIL RECORD",
        "project": project, "response_id": response.id, "participant_id": response.participant_id,
        "observed_at": response.submitted_at.isoformat(), "caption": caption,
        "artefact_index": index,
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _seed_media(db: Session, storage, organisation_id: int, study: Study, responses: list[ActivityResponse], *, project_key: str, target: int, counts: SeedCounts) -> None:
    image_assets = {
        "everyday": ["rivermere_bus_interchange_delay.jpg", "rivermere_market_square_bench.jpg"],
        "chapel": ["chapel_lane_reversing_hgv.jpg", "chapel_lane_floodlight.jpg"],
    }[project_key]
    for index, response in enumerate(responses[:target]):
        if index < len(image_assets):
            asset = ASSET_ROOT / image_assets[index]
            with asset.open("rb") as source:
                _save_evidence(db, storage, organisation_id=organisation_id, study=study, response=response, original_name=image_assets[index], stream=source, content_type="image/jpeg", counts=counts)
        else:
            caption = (
                f"Context note for ordinary Rivermere observation {index + 1}; linked to the submitted field entry."
                if project_key == "everyday"
                else f"Fictional resident incident-log artefact {index + 1}; records observation and reporting labour without imitating a council document."
            )
            name = f"{project_key}_field_artefact_{index + 1:02d}.txt"
            _save_evidence(db, storage, organisation_id=organisation_id, study=study, response=response, original_name=name, stream=io.BytesIO(_artifact_bytes(project=project_key, response=response, index=index + 1, caption=caption)), content_type="text/plain", counts=counts)


def _ensure_operator(db: Session, organisation: Organisation, counts: SeedCounts) -> User:
    operator = db.scalar(select(User).where(User.is_active.is_(True), User.role.in_(["owner", "admin"])).order_by(User.id))
    if not operator:
        operator = User(
            organisation_id=organisation.id, name="Rivermere Demo Researcher",
            email="researcher@rivermere.demo.invalid", password_hash=None, role="owner", is_active=True,
        )
        db.add(operator); db.flush()
    membership = db.scalar(select(OrganisationMembership).where(OrganisationMembership.user_id == operator.id, OrganisationMembership.organisation_id == organisation.id))
    if not membership:
        db.add(OrganisationMembership(user_id=operator.id, organisation_id=organisation.id, role="owner", is_active=True))
        counts.memberships += 1
    return operator


def seed_rivermere(db: Session, storage) -> SeedCounts:
    """Idempotently add missing Rivermere records without overwriting existing rows."""
    counts = SeedCounts()
    organisation = db.scalar(select(Organisation).where(Organisation.slug == RIVERMERE_SLUG))
    if not organisation:
        organisation = Organisation(name="Rivermere Town Council (Fictional Demo)", slug=RIVERMERE_SLUG, created_at=_now("2025-08-01T09:00:00"))
        db.add(organisation); db.flush()
    operator = _ensure_operator(db, organisation, counts)

    everyday_project = _get_or_create_project(
        db, organisation.id, operator.id, code=EVERYDAY_PROJECT_CODE,
        title="Rivermere 2035: Everyday Life and the Future of Our Town",
        description="Fictional longitudinal ethnography of routines, place, relationships, inequality, infrastructure and civic trust across Rivermere.", counts=counts,
    )
    everyday_study = _get_or_create_study(
        db, organisation.id, operator.id, everyday_project, code=EVERYDAY_STUDY_CODE,
        title="Everyday Rivermere longitudinal field study",
        description="Sixteen weeks of situated diaries, journeys, place observations and photo elicitation. Accounts retain disagreement and changing interpretation.",
        start=_now("2026-01-12T00:00:00"), end=_now("2026-05-03T23:59:00"), counts=counts,
    )
    everyday_people = _participants(db, organisation.id, operator.id, EVERYDAY_PARTICIPANTS, everyday_study, counts, chapel=False)
    everyday_activities = _activities(db, organisation.id, everyday_study, EVERYDAY_PROMPTS, 7, counts)
    everyday_responses: list[ActivityResponse] = []
    weekly_counts = [5, 8, 6, 9, 7, 6, 8, 5, 9, 7, 6, 8, 7, 5, 8, 8]
    for week, (activity, weekly_count) in enumerate(zip(everyday_activities, weekly_counts, strict=True)):
        selected_indices = [((week * 3) + (offset * 7)) % len(everyday_people) for offset in range(weekly_count)]
        for person_index in selected_indices:
            participant = everyday_people[person_index]
            text, entry_type, place, codes = _everyday_text(EVERYDAY_PARTICIPANTS[person_index], week)
            observed = everyday_study.start_at + timedelta(days=week * 7 + (person_index * 2 + week) % 6, hours=7 + (person_index % 11))
            everyday_responses.append(_response(db, organisation.id, everyday_study, activity, participant, text=text, entry_type=entry_type, place=place, codes=codes, observed_at=observed, phase=f"week_{week + 1:02d}", counts=counts))
    everyday_responses.sort(key=lambda row: row.submitted_at)
    _seed_media(db, storage, organisation.id, everyday_study, everyday_responses, project_key="everyday", target=36, counts=counts)

    chapel_project = _get_or_create_project(
        db, organisation.id, operator.id, code=CHAPEL_PROJECT_CODE,
        title="Chapel Lane: Living With an Unresolved Planning Breach",
        description="Fictional longitudinal ethnography of resident observation, reporting labour, process opacity, fatigue, adaptation and apparent non-resolution.", counts=counts,
    )
    chapel_study = _get_or_create_study(
        db, organisation.id, operator.id, chapel_project, code=CHAPEL_STUDY_CODE,
        title="Chapel Lane resident observation study",
        description="Twelve monthly phases trace uncertainty, collective interpretation, active reporting, fatigue, non-reporting and persistence of the underlying issue.",
        start=_now("2025-08-18T00:00:00"), end=_now("2026-07-19T23:59:00"), counts=counts,
    )
    chapel_people = _participants(db, organisation.id, operator.id, CHAPEL_PARTICIPANTS, chapel_study, counts, chapel=True)
    chapel_activities = _activities(db, organisation.id, chapel_study, CHAPEL_PROMPTS, 28, counts)
    chapel_responses: list[ActivityResponse] = []
    for month, activity in enumerate(chapel_activities):
        for person_index, participant in enumerate(chapel_people):
            # Each core participant misses two non-adjacent check-ins: 14 × 10 = 140 entries.
            if month in {person_index % 12, (person_index + 5) % 12}:
                continue
            text, entry_type, place, codes = _chapel_text(CHAPEL_PARTICIPANTS[person_index], month)
            observed = chapel_study.start_at + timedelta(days=month * 28 + (person_index * 3 + month) % 12, hours=6 + (person_index % 13))
            chapel_responses.append(_response(db, organisation.id, chapel_study, activity, participant, text=text, entry_type=entry_type, place=place, codes=codes, observed_at=observed, phase=CHAPEL_SCENES[month][0], counts=counts))
    chapel_responses.sort(key=lambda row: row.submitted_at)
    _seed_media(db, storage, organisation.id, chapel_study, chapel_responses, project_key="chapel", target=48, counts=counts)

    db.add(AuditEvent(
        organisation_id=organisation.id, actor_user_id=operator.id, action="demo.rivermere.seeded",
        entity_type="organisation", entity_id=str(organisation.id),
        detail=(f"fictional_demo=true projects={counts.projects} studies={counts.studies} participants={counts.participants} "
                f"entries={counts.entries} media={counts.media}; AI analysis jobs not fabricated"),
    ))
    db.commit()
    return counts


def project_analysis_manifest(project_code: str) -> dict[str, object]:
    if project_code == EVERYDAY_PROJECT_CODE:
        codes = sorted({code for scene in EVERYDAY_SCENES for code in scene[3].split("|")})
        return {"project_code": project_code, "codebook": codes, "memos": EVERYDAY_MEMOS, "ai_analysis_records": 0}
    if project_code == CHAPEL_PROJECT_CODE:
        codes = sorted({code for scene in CHAPEL_SCENES for code in scene[3].split("|")})
        return {"project_code": project_code, "codebook": codes, "memos": CHAPEL_MEMOS, "ai_analysis_records": 0}
    raise ValueError("Unknown Rivermere project code")


def remove_rivermere_project(db: Session, storage, project_code: str) -> dict[str, int]:
    """Remove one deterministic demo project and only records owned by its study."""
    if project_code not in {EVERYDAY_PROJECT_CODE, CHAPEL_PROJECT_CODE}:
        raise ValueError("Cleanup is restricted to a known Rivermere demonstration project code.")
    organisation = db.scalar(select(Organisation).where(Organisation.slug == RIVERMERE_SLUG))
    if not organisation:
        return {"projects": 0, "studies": 0, "participants": 0, "media": 0}
    project = db.scalar(select(Project).where(Project.organisation_id == organisation.id, Project.code == project_code))
    if not project:
        return {"projects": 0, "studies": 0, "participants": 0, "media": 0}
    studies = db.scalars(select(Study).where(Study.organisation_id == organisation.id, Study.project_id == project.id)).all()
    study_ids = [row.id for row in studies]
    media_rows = db.scalars(select(EvidenceFile).where(EvidenceFile.organisation_id == organisation.id, EvidenceFile.study_id.in_(study_ids))).all() if study_ids else []
    for evidence in media_rows:
        storage.delete(evidence.stored_name)
    if study_ids:
        invitation_ids = db.scalars(select(ParticipantInvitation.id).where(ParticipantInvitation.study_id.in_(study_ids))).all()
        if invitation_ids:
            db.execute(delete(PublicAuthSession).where(PublicAuthSession.participant_invitation_id.in_(invitation_ids)))
        for model in [EvidenceConfidenceAssessment, ResearchTheme, ResearchAnalysisSuggestion, EvidenceFile, ParticipantMessage, ParticipantInvitation, ActivityResponse, StudyAccess, StudyMethodologyConfiguration, StudyGovernance, StudyEnrolment, Activity]:
            db.execute(delete(model).where(model.study_id.in_(study_ids)))
        db.execute(delete(Study).where(Study.id.in_(study_ids)))
    db.delete(project)
    orphan_ids = db.scalars(
        select(Participant.id).where(
            Participant.organisation_id == organisation.id,
            Participant.tags.like("%fictional-demo%"),
        )
    ).all()
    removed_participants = 0
    for participant_id in orphan_ids:
        if not db.scalar(select(func.count(StudyEnrolment.id)).where(StudyEnrolment.participant_id == participant_id)):
            participant = db.get(Participant, participant_id)
            if participant:
                db.delete(participant); removed_participants += 1
    db.add(AuditEvent(
        organisation_id=organisation.id, actor_user_id=None, action="demo.rivermere.project_removed",
        entity_type="project", entity_id=project_code, detail="Project-specific fictional demo cleanup completed.",
    ))
    db.commit()
    return {"projects": 1, "studies": len(studies), "participants": removed_participants, "media": len(media_rows)}
