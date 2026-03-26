"""
export_leads_by_sector.py — Lead veritabanından sektör bazlı CSV export
Her sektör için ayrı bir CSV dosyası oluşturur.
"""
import os
import csv
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "smartmailer_ultimate.db")
EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")

COLUMNS = [
    "email", "company", "sector", "location", "vehicles",
    "phone", "website", "score", "ai_score", "status",
    "contact_person", "source", "created_at"
]


def export_leads():
    """Tüm lead'leri sektör bazlı CSV dosyalarına export eder."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # Sektör bazlı lead sayılarını al
    sectors = conn.execute(
        "SELECT COALESCE(NULLIF(sector,''), 'onbekend') as sector, COUNT(*) as cnt "
        "FROM leads GROUP BY COALESCE(NULLIF(sector,''), 'onbekend') ORDER BY cnt DESC"
    ).fetchall()

    total_exported = 0
    files_created = []

    for row in sectors:
        sector = row["sector"]
        count = row["cnt"]

        # Dosya adı — güvenli karakter
        safe_name = sector.lower().replace(" ", "_").replace("/", "_").replace("&", "en")
        filename = f"leads_{safe_name}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)

        # Bu sektördeki lead'leri çek
        if sector == "onbekend":
            leads = conn.execute(
                f"SELECT {','.join(COLUMNS)} FROM leads WHERE sector IS NULL OR sector = '' ORDER BY ai_score DESC, score DESC"
            ).fetchall()
        else:
            leads = conn.execute(
                f"SELECT {','.join(COLUMNS)} FROM leads WHERE sector = ? ORDER BY ai_score DESC, score DESC",
                (sector,)
            ).fetchall()

        # CSV yaz
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(COLUMNS)
            for lead in leads:
                writer.writerow([lead[col] for col in COLUMNS])

        files_created.append((filename, count))
        total_exported += count
        print(f"  ✓ {filename:40s} — {count:>6,} leads")

    # Ayrıca tüm lead'leri tek dosyada
    all_leads = conn.execute(
        f"SELECT {','.join(COLUMNS)} FROM leads ORDER BY sector, ai_score DESC, score DESC"
    ).fetchall()

    all_filepath = os.path.join(EXPORT_DIR, "leads_ALLES.csv")
    with open(all_filepath, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(COLUMNS)
        for lead in all_leads:
            writer.writerow([lead[col] for col in COLUMNS])

    conn.close()

    print(f"\n{'='*60}")
    print(f"  TOTAAL: {total_exported:,} leads verdeeld over {len(files_created)} sectoren")
    print(f"  + leads_ALLES.csv met alle leads ({len(all_leads):,})")
    print(f"  Export map: {os.path.abspath(EXPORT_DIR)}")
    print(f"{'='*60}\n")

    return files_created


if __name__ == "__main__":
    print("\n🔄 Lead export per sector gestart...\n")
    export_leads()
    print("✅ Klaar!")
