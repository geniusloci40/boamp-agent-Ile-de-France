import os
import sys
import requests
import json
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from anthropic import Anthropic

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENT = os.getenv("EMAIL_RECIPIENT")

IDF_DEPT = ["75", "77", "78", "91", "92", "93", "94", "95"]
BOAMP_BASE = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/exports/json"

def fetch_tenders():
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    params = [
        ("lang", "fr"),
        ("refine", 'nature_categorise_libelle:"Avis de marché"'),
        ("q", "maitrise oeuvre architecture"),
        ("where", f'dateparution >= "{three_days_ago}"'),
        ("limit", "100"),
        ("timezone", "Europe/Paris"),
    ]
    try:
        resp = requests.get(BOAMP_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            print(f"  → API response: {len(data)} totali", flush=True)
            return data
        else:
            print(f"  → API response: {data.get('total_count', 0)} totali", flush=True)
            return data.get("results", [])
    except Exception as e:
        print(f"[ERRORE] Fetch BOAMP: {e}", flush=True)
        return []

def filter_idf(tenders):
    result = []
    for t in tenders:
        dept = (t.get("code_departement") or "")
        lieu = (t.get("lieuexecution") or "").lower()
        if dept in IDF_DEPT:
            result.append(t)
        elif any(n in lieu for n in ["paris", "seine", "essonne", "yvelines", "val-de-marne", "hauts-de-seine", "val-d'oise", "seine-et-marne"]):
            result.append(t)
    return result if result else tenders

def assess_relevance(tenders):
    if not tenders:
        return []

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[INFO] ANTHROPIC_API_KEY non trovata — invio tutti gli annunci", flush=True)
        for t in tenders:
            t["_motivo"] = "Filtro AI non attivo"
            t["_missione"] = "—"
        return tenders

    client = Anthropic()
    batch = [
        {
            "id": t.get("idweb", ""),
            "titre": t.get("titre", ""),
            "objet": (t.get("objet") or "")[:400],
            "acheteur": t.get("nomacheteur", ""),
            "lieu": t.get("lieuexecution") or t.get("code_departement", "")
        }
        for t in tenders
    ]
    prompt = f"""Sei un assistente per uno studio di architettura parigino specializzato in edifici scolastici e pubblici (scuole, asili, uffici comunali, mediateche, centri culturali, impianti sportivi) in Île-de-France.
Sono pertinenti: concorsi di progettazione, incarichi MOE completi, MOE parziali, missioni di conception.
Non sono pertinenti: forniture, lavori senza progettazione, AMO pura, études sans maîtrise d'oeuvre.

Rispondi SOLO con un JSON array, senza testo aggiuntivo:
[{{"id": "...", "pertinente": true/false, "motivo": "max 15 parole", "missione": "tipo missione"}}]

Annunci:
{json.dumps(batch, ensure_ascii=False)}"""
    try:
        response = client.messages.create(
           model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        assessments = json.loads(raw)
    except Exception as e:
        print(f"[ERRORE] Claude: {e}", flush=True)
        assessments = [{"id": t.get("idweb"), "pertinente": True, "motivo": "Valutazione non disponibile", "missione": "—"} for t in tenders]

    assessment_map = {a["id"]: a for a in assessments}
    relevant = []
    for t in tenders:
        a = assessment_map.get(t.get("idweb", ""), {})
        if a.get("pertinente", False):
            t["_motivo"] = a.get("motivo", "")
            t["_missione"] = a.get("missione", "—")
            relevant.append(t)
    return relevant

def send_email(tenders):
    today = datetime.now().strftime("%d/%m/%Y")
    count = len(tenders)
    subject = f"BOAMP IDF · {count} appalto{'i' if count != 1 else ''} rilevante{'i' if count != 1 else ''} — {today}"

    if count == 0:
        body = "<p style='color:#666'>Nessun appalto pertinente negli ultimi 3 giorni in Île-de-France.</p>"
    else:
        cards = ""
        for t in tenders:
            url = f"https://www.boamp.fr/avis/detail/{t.get('idweb', '')}"
            lieu = t.get("lieuexecution") or t.get("code_departement", "—")
            cards += f"""<div style="border:1px solid #e0e0e0;border-radius:6px;padding:16px;margin-bottom:16px;">
<p style="margin:0 0 4px;font-size:13px;color:#888;">{t.get('dateparution', '')} · {lieu}</p>
<h3 style="margin:0 0 8px;font-size:16px;"><a href="{url}" style="color:#1a1a1a;text-decoration:none;">{t.get('titre', '—')}</a></h3>
<p style="margin:0 0 6px;font-size:13px;color:#444;">
<strong>Acheteur:</strong> {t.get('nomacheteur', '—')}<br>
<strong>Missione:</strong> {t.get('_missione', '—')}<br>
<strong>Nota AI:</strong> {t.get('_motivo', '—')}
</p>
<p style="font-size:13px;color:#555;">{(t.get('objet') or '')[:300]}</p>
<a href="{url}" style="display:inline-block;margin-top:10px;font-size:12px;background:#1a1a1a;color:#fff;padding:6px 14px;border-radius:4px;text-decoration:none;">Apri su BOAMP →</a>
</div>"""
        body = cards

    html = f"""<!DOCTYPE html><html><body style="font-family:-apple-system,sans-serif;max-width:680px;margin:0 auto;padding:24px;">
<h2 style="font-size:18px;margin-bottom:4px;">Digest Architettura — Île-de-France</h2>
<p style="font-size:13px;color:#888;margin:0 0 24px;">Île-de-France · {today} · {count} risultato{'i' if count != 1 else ''}</p>
{body}
<hr style="border:none;border-top:1px solid #eee;margin-top:32px;">
<p style="font-size:11px;color:#aaa;">Fonte: BOAMP · Keyword: architecture maîtrise d'oeuvre · Filtro AI: Claude</p>
</body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = EMAIL_RECIPIENT
        msg.attach(MIMEText(html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        print(f"[OK] Email inviata a {EMAIL_RECIPIENT}", flush=True)
    except Exception as e:
        print(f"[ERRORE] Email: {e}", flush=True)

def main():
    print(f"Python {sys.version}", flush=True)
    print("Script avviato", flush=True)
    today = datetime.now().strftime("%d/%m/%Y")
    print(f"[{today}] Avvio ricerca BOAMP IDF...", flush=True)
    raw = fetch_tenders()
    print(f"  → {len(raw)} annunci trovati", flush=True)
    idf = filter_idf(raw)
    print(f"  → {len(idf)} in Île-de-France", flush=True)
    relevant = assess_relevance(idf)
    print(f"  → {len(relevant)} pertinenti", flush=True)
    send_email(relevant)

if __name__ == "__main__":
    main()
