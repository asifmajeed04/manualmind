r"""Generates two small test documents (German manual, English datasheet) into eval/docs_sample/ (kept apart from the real manuals in eval/docs/).

Real public manuals should be added next to them — see eval/README.md.
Usage (from repo root):  ai-service\.venv\Scripts\python eval\make_sample_docs.py
"""

from pathlib import Path

import pymupdf

DOCS = {
    "Kreiselpumpe_KP-300_Betriebsanleitung.pdf": [
        "Betriebsanleitung Kreiselpumpe KP-300\n\n1. Sicherheitshinweise\n"
        "Vor allen Wartungsarbeiten die Pumpe vom Netz trennen und gegen Wiedereinschalten sichern. "
        "Druck im System vollständig abbauen. Nur geschultes Fachpersonal darf Arbeiten an der Anlage "
        "durchführen. Schutzbrille und Schutzhandschuhe tragen.",
        "2. Technische Daten\nFördermenge: max. 300 l/min\nFörderhöhe: max. 45 m\nMotorleistung: 4,0 kW\n"
        "Zulässige Medientemperatur: 0 bis 80 °C\nGewicht: 62 kg\nSchutzart: IP55",
        "3. Wartung\nDie Gleitringdichtung ist alle 500 Betriebsstunden auf Leckage zu prüfen. "
        "Das Wälzlager wird alle 2000 Betriebsstunden mit Lithiumfett nachgeschmiert. "
        "Ersatzteil Drucksensor: 6ES7 214-1AG40-0XB0. Ersatzteil Gleitringdichtung: GD-300-11.",
        "4. Störungen\nFehlercode E42: Überdruck im System. Ursache: Druckventil verstopft oder Absperrschieber "
        "auf der Druckseite geschlossen. Abhilfe: Ventil reinigen, Absperrschieber öffnen, Drucksensor prüfen.\n"
        "Fehlercode E17: Motor überhitzt. Ursache: Lüfter verschmutzt oder Umgebungstemperatur über 40 °C. "
        "Abhilfe: Lüfter reinigen und Belüftung verbessern.",
    ],
    "DP-50_Dosing_Pump_Datasheet.pdf": [
        "Dosing Pump DP-50 — Datasheet\n\nTechnical data\nMax. pressure: 10 bar\nFlow rate: 50 l/h\n"
        "Motor: 0.37 kW, 230 V\nControl: 4–20 mA input\nController part number: 6ES7 214-1BG40-0XB0\n"
        "Operating temperature: 5–40 °C",
        "Installation\nMount the pump horizontally on a vibration-free base. The suction line must not exceed 2 m. "
        "Install a pressure relief valve set to 12 bar on the discharge side.",
        "Troubleshooting\nError E41: low flow — check the suction line for air and clean the foot valve.\n"
        "Error E43: motor stall — check the motor and the gearbox for blockage.\n"
        "Maintenance: replace the diaphragm every 4000 operating hours.",
    ],
}


def main() -> None:
    out = Path(__file__).parent / "docs_sample"
    out.mkdir(exist_ok=True)
    for name, pages in DOCS.items():
        doc = pymupdf.open()
        for text in pages:
            doc.new_page().insert_textbox(pymupdf.Rect(50, 50, 550, 800), text, fontsize=11)
        doc.save(out / name)
        doc.close()
        print(f"wrote eval/docs_sample/{name} ({len(pages)} pages)")


if __name__ == "__main__":
    main()
