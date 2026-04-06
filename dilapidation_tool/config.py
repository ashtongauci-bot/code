# config.py - Edit these details before running

PROJECT = {
    "address": "81-85 Campbell Street, SURRY HILLS, NSW, 2010",
    "client": "Justus Group",
    "inspector_name": "Oscar Gutierrez",
    "inspector_quals": "BE (Civil), MIEAust.",
    "reviewer_name": "Dr Ali Amin",
    "reviewer_quals": "BE (Hons. 1), PhD, MIEAust., CPEng. NER, RPEQ",
    "company": "Acroyali Engineering",
    "inspection_date": "Wednesday 25th of March 2026",
    "report_date": "13/03/2026",
    "ref": "RS2401-D06[A]",
    "total_photos": 123,
    "photo_link": "Insert photo link here",
    "streets_inspected": "Mary Street, Campbell Street, Foster Street and Hands Lane",
}

# Your Anthropic API key
ANTHROPIC_API_KEY = "your-api-key-here"

# Photo folders and their section labels (in report order)
PHOTO_SECTIONS = [
    ("northern_end", "NORTHERN END"),
    ("eastern_side", "EASTERN SIDE"),
    ("southern_end", "SOUTHERN END"),
    ("western_side", "WESTERN SIDE"),
]
