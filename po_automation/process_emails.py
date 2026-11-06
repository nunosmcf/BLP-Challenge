"""CLI: process one email file or all emails in the inbox folder.

Usage:
    python process_emails.py                     # process all unprocessed emails
    python process_emails.py emails/email_05.eml # process one specific file
"""
import sys
from pathlib import Path

# Allow running from the project root
sys.path.insert(0, str(Path(__file__).parent))

from src import config, database, workflow


def main():
    database.init_db()

    if len(sys.argv) > 1:
        targets = [Path(sys.argv[1])]
    else:
        targets = sorted(config.EMAILS_DIR.glob("*.eml"))

    if not targets:
        print("No .eml files found.")
        return

    already = {r["email_file"] for r in database.all_requisitions()}

    for eml in targets:
        if eml.name in already and len(sys.argv) == 1:
            print(f"  skip  {eml.name}  (already processed)")
            continue
        print(f"  process  {eml.name} ...", end=" ", flush=True)
        rid = workflow.process_email(eml)
        req = database.get_requisition(rid)
        print(f"{req['state']}  ->  {rid[:8]}...")

    print("\nDone. Run 'streamlit run app.py' to view results.")


if __name__ == "__main__":
    main()
