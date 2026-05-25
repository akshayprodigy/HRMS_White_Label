"""
Seed holidays (FY 2026-27) and company policies for United Exploration India Pvt Ltd.
Policies are created as DB records with placeholder PDF files.
Run: docker compose -f docker-compose.prod.yml exec -T -w /app -e PYTHONPATH=/app backend python scripts/seed_holidays_and_policies.py
"""
import asyncio
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models.hr import HolidayCalendar, PolicyDocument
from app.core.config import settings


# ── Indian holidays for FY 2026-27 (Apr 2026 – Mar 2027) ──────────────
HOLIDAYS = [
    # April 2026
    ("Ram Navami", "2026-04-02", "All", False),
    ("Mahavir Jayanti", "2026-04-06", "All", False),
    ("Good Friday", "2026-04-03", "All", False),
    ("Dr. Ambedkar Jayanti", "2026-04-14", "All", False),
    # May 2026
    ("May Day", "2026-05-01", "All", False),
    ("Buddha Purnima", "2026-05-12", "All", False),
    # June 2026
    ("Rath Yatra", "2026-06-23", "All", True),
    # July 2026
    ("Eid ul-Adha (Bakrid)", "2026-07-07", "All", False),
    # August 2026
    ("Muharram", "2026-08-06", "All", False),
    ("Independence Day", "2026-08-15", "All", False),
    ("Janmashtami", "2026-08-25", "All", False),
    ("Raksha Bandhan", "2026-08-22", "All", True),
    # September 2026
    ("Milad-un-Nabi", "2026-09-05", "All", False),
    # October 2026
    ("Mahatma Gandhi Jayanti", "2026-10-02", "All", False),
    ("Dussehra (Vijaya Dashami)", "2026-10-20", "All", False),
    ("Durga Puja (Saptami)", "2026-10-17", "All", False),
    ("Durga Puja (Ashtami)", "2026-10-18", "All", False),
    ("Durga Puja (Navami)", "2026-10-19", "All", False),
    # November 2026
    ("Diwali (Lakshmi Puja)", "2026-11-08", "All", False),
    ("Diwali (Govardhan Puja)", "2026-11-09", "All", False),
    ("Bhai Dooj", "2026-11-10", "All", True),
    ("Guru Nanak Jayanti", "2026-11-18", "All", False),
    ("Chhath Puja", "2026-11-12", "All", True),
    # December 2026
    ("Christmas", "2026-12-25", "All", False),
    # January 2027
    ("New Year", "2027-01-01", "All", False),
    ("Republic Day", "2027-01-26", "All", False),
    ("Makar Sankranti", "2027-01-14", "All", True),
    # February 2027
    ("Vasant Panchami", "2027-02-01", "All", True),
    # March 2027
    ("Maha Shivaratri", "2027-03-11", "All", False),
    ("Holi", "2027-03-25", "All", False),
]


# ── Policies ──────────────────────────────────────────────────────────
POLICIES = [
    {
        "title": "Time Office Policy",
        "version": "2.0",
        "description": (
            "HR-UEIPL-02/2024-25 — Effective 1 Apr 2024. "
            "Covers office attendance, leave categories (CL 10 days, PL 14 days, SL 7 days, Comp Off), "
            "weekly off (Sundays + 2nd & 4th Saturdays), office hours 10:15 AM – 6:30 PM, "
            "tardiness rules, maternity leave as per Maternity Act 1961, and general leave rules."
        ),
    },
    {
        "title": "Office Etiquette Policy",
        "version": "1.0",
        "description": (
            "UEIPL/officeetiquette/ver-1.0 — Effective 14 May 2024. "
            "Covers general conduct, professionalism, communication etiquette (email & phone), "
            "office environment (cleanliness, noise control, shared spaces), meeting conduct, "
            "use of company resources, interpersonal relations, anti-discrimination & harassment, "
            "safety compliance, and disciplinary actions."
        ),
    },
    {
        "title": "Travel & Conveyance Policy",
        "version": "1.19",
        "description": (
            "HR-UEIPL-01/2020-21 — Effective 1 Feb 2020. "
            "Covers local travel (car @ INR 10/km), domestic travel (train/air entitlements), "
            "lodging limits by city tier (Tier-A/B/C), food & beverage allowances, "
            "miscellaneous expenses (INR 50/day), international travel guidelines, "
            "pre-travel formalities, cancellations, and post-travel expense settlement."
        ),
    },
    {
        "title": "Email Policy",
        "version": "1.0",
        "description": (
            "Corporate email usage policy. Covers appropriate and inappropriate use of company email, "
            "personal use guidelines, email security (strong passwords, phishing awareness), "
            "email signature standards, and disciplinary actions for non-compliance."
        ),
    },
]


def _create_placeholder_pdf(title: str) -> bytes:
    """Create a minimal valid PDF with just the policy title."""
    # Minimal valid PDF structure
    content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 24 Tf 72 700 Td ({title}) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000360 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
431
%%EOF"""
    return content.encode("latin-1")


async def main():
    async with SessionLocal() as db:
        # ── Holidays ─────────────────────────────────────────────────
        existing_count = (await db.execute(text("SELECT COUNT(*) FROM holidaycalendar"))).scalar()
        if existing_count and existing_count > 0:
            print(f"Holidays table already has {existing_count} records — skipping.")
        else:
            for name, dt, location, is_optional in HOLIDAYS:
                db.add(HolidayCalendar(
                    name=name,
                    date=date.fromisoformat(dt),
                    location=location,
                    is_optional=is_optional,
                    description=f"{'Optional holiday' if is_optional else 'Gazetted holiday'} — FY 2026-27",
                ))
            await db.flush()
            print(f"Inserted {len(HOLIDAYS)} holidays for FY 2026-27.")

        # ── Policies ─────────────────────────────────────────────────
        existing_titles = set()
        result = await db.execute(select(PolicyDocument.title))
        for row in result.scalars():
            existing_titles.add(row)

        policy_dir = Path(settings.POLICY_DOCUMENTS_DIR)
        policy_dir.mkdir(parents=True, exist_ok=True)

        added = 0
        for pol in POLICIES:
            if pol["title"] in existing_titles:
                print(f"  Policy '{pol['title']}' already exists — skipping.")
                continue

            # Create placeholder PDF file
            safe_name = pol["title"].lower().replace(" ", "_").replace("&", "and")
            stored_name = f"{uuid4().hex}_{safe_name}.pdf"
            dest = policy_dir / stored_name
            dest.write_bytes(_create_placeholder_pdf(pol["title"]))

            db.add(PolicyDocument(
                title=pol["title"],
                description=pol["description"],
                file_url=stored_name,
                version=pol["version"],
                is_active=True,
            ))
            added += 1
            print(f"  Added policy: {pol['title']} (v{pol['version']})")

        if added == 0:
            print("No new policies to add.")
        else:
            print(f"Inserted {added} policies.")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
