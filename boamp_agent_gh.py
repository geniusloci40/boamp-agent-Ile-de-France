import os
import requests
import json
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from anthropic import Anthropic

def fetch_boamp_notices():
    """Scarica annunci BOAMP API per architettura, ultimi 3 giorni, Île-de-France"""
    
    # Codici postali Île-de-France (75, 77, 78, 91, 92, 93, 94, 95)
    idf_postcodes = ["75", "77", "78", "91", "92", "93", "94", "95"]
    
    # CPV architettura: 71220000, 71221000
    cpv_codes = ["71220000", "71221000"]
    
    base_url = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
    
    all_notices = []
    
    for cpv in cpv_codes:
        # Ultimi 3 giorni
        three_days_ago = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Query per CPV e data
        where_clause = f"cpv_code LIKE '{cpv}%' AND publication_date >= '{three_days_ago}'"
        
        params = {
            "where": where_clause,
            "order_by": "publication_date DESC",
            "limit": 100
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Filtra per codici postali Île-de-France
            for record in data.get("results", []):
                postal_code = record.get("postal_code", "")[:2]
                if postal_code in idf_postcodes:
                    all_notices.append(record)
        
        except requests.exceptions.RequestException as e:
            print(f"Errore nella richiesta BOAMP: {e}")
    
    return all_notices

def evaluate_with_claude(notices):
    """Passa gli annunci a Claude per valutazione pertinenza"""
    
    if not notices:
        return []
    
    client = Anthropic()
    
    # Prepara il testo degli annunci
    notices_text = ""
    for i, notice in enumerate(notices, 1):
        notices_text += f"""
Annuncio {i}:
- Titolo: {notice.get('title', 'N/A')}
- Ente: {notice.get('contracting_body', 'N/A')}
- CPV: {notice.get('cpv_code', 'N/A')}
- Descrizione: {notice.get('object', 'N/A')[:300]}
- Data pubblicazione: {notice.get('publication_date', 'N/A')}
- Link: {notice.get('notice_url', 'N/A')}
"""
    
    prompt = f"""Sei un esperto di appalti pubblici francesi per architettura.

Analizza questi annunci BOAMP di Île-de-France e identifica quelli più pertinenti per uno studio di architettura interessato a progetti di progettazione/costruzione di edifici pubblici (scuole, asili, uffici, strutture scolastiche).

{notices_text}

Per ogni annuncio, rispondi in JSON così:
{{"numero": N, "pertinente": true/false, "motivo": "breve spiegazione"}}

Rispondi SOLO con un array JSON, niente altro."""
    
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # Estrai la risposta
        response_text = response.content[0].text
        
        # Prova a parsare JSON
        evaluations = json.loads(response_text)
        
        # Filtra solo i pertinenti
        relevant_notices = []
        for eval_item in evaluations:
            if eval_item.get("pertinente"):
                numero =...