import os
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

BOAMP_API = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
IDF_DEPT = ["75", "77", "78", "91", "92", "93", "94", "95", "60"]

def fetch_tenders():
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d")
    
    base = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/exports/json"
    
    params = [
        ("lang", "fr"),
        ("refine", 'nature_categorise_libelle:"Avis de marché"'),
        ("q", "maitrise oeuvre architecture"),
        ("where", f'dateparution >= "{three_days_ago}"'),
        ("limit", "100"),
        ("timezone", "Europe/Paris"),
    ]
    
    try:
        resp = requests.get(base, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # exports/json restituisce una lista diretta, non un dict con results
        if isinstance(data, list):
            print(f"  → API response: {len(data)} totali")
            return data
        else:
            print(f"  → API response: {data.get('total_count', 0)} totali")
            return data.get("results", [])
    except Exception as e:
        print(f"[ERRORE] Fetch BOAMP: {e}")
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
        print("[INFO] ANTHROPIC_API_KEY non trovata — filtro AI disabilitato, invio tutti gli annunci")
        for t in tenders:
            t["_motivo"] = "Filtro AI non attivo"
            t
