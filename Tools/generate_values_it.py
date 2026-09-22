#!/usr/bin/env python3
"""Fill android/.../values-it/strings.xml from the English resources.

Incremental by default: existing Italian values are kept, so a later upstream
sync can add only the new keys. Pass --force to regenerate every key.

Translations come from a small hand-written override table (navigation,
onboarding, terms, and other first-run copy) and, for everything else, from
Google Translate with product terms shielded so Charge / Effort / Rest / strap
do not drift. Format specifiers are shielded the same way and checked before
a value is written. If a translation drops a specifier, the English source is
kept and reported — Android will still compile, and the echo audit will see it.

Network is required only for keys that are not already translated and not in
the override table. The unofficial translate endpoint is best-effort; a fork
sync that cannot reach it leaves those keys in English and exits non-zero
only when --strict is set.
"""
from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "android/app/src/main/res/values/strings.xml"
OUT = ROOT / "android/app/src/main/res/values-it/strings.xml"
CACHE = Path("/tmp/noop-it-translation-cache.json")

SPEC_RE = re.compile(r"%(?:\d+\$)?[-+0 #,(]*\d*(?:\.\d+)?[sdifoxXeEgGcC]|%%")

# Brands and sigils the translator rewrites (WHOOP → "OPPURE"). Numeric tokens
# survive; letter tokens get "corrected" into Italian words.
BRANDS: list[tuple[str, str, str]] = [
    ("Health Connect", "QZ10", "Health Connect"),
    ("Apple Health", "QZ11", "Apple Health"),
    ("Bluetooth Low Energy", "QZ12", "Bluetooth Low Energy"),
    ("Bluetooth", "QZ13", "Bluetooth"),
    ("SpO₂", "QZ14", "SpO₂"),
    ("SpO2", "QZ15", "SpO2"),
    ("VO₂max", "QZ16", "VO₂max"),
    ("VO2max", "QZ17", "VO2max"),
    ("WHOOP", "QZ18", "WHOOP"),
    ("NOOP", "QZ19", "NOOP"),
    ("Oura", "QZ20", "Oura"),
    ("Strava", "QZ21", "Strava"),
    ("Garmin", "QZ22", "Garmin"),
    ("Fitbit", "QZ23", "Fitbit"),
    ("HRV", "QZ24", "HRV"),
    ("GPS", "QZ25", "GPS"),
]

# Score names Google otherwise renders as billing ("Addebito") or tension.
INLINE_TERMS: list[tuple[str, str]] = [
    (r"\bStrain\b", "Sforzo"),
    (r"\bstrain\b", "sforzo"),
    (r"\bCharge\b", "Carica"),
    (r"\bcharge\b", "carica"),
]

# First-run and navigation copy, written by hand. Wins over machine translation.
OVERRIDES: dict[str, str] = {
    "app_name": "NOOP IT",
    "widget_description": "Riposo, Carica e Sforzo di oggi, con frequenza cardiaca dal vivo e batteria della fascia.",
    "widget_hr_name": "Frequenza cardiaca NOOP",
    "widget_hr_description": "Frequenza cardiaca dal vivo, con le ultime tre ore come traccia.",
    "widget_stress_name": "Stress NOOP",
    "widget_stress_description": "Lo stress di oggi, ora per ora.",
    "widget_compact_name": "NOOP Compatto",
    "widget_compact_description": "Widget compatto di Riposo, Carica e Sforzo, con frequenza cardiaca dal vivo e batteria della fascia.",
    "widget_error": "Il widget NOOP non ha potuto disegnarsi: si riprende al prossimo aggiornamento.",
    "nav_today": "Oggi",
    "nav_intelligence": "Intelligence",
    "nav_coupled_view": "Vista accoppiata",
    "nav_live": "Dal vivo",
    "nav_intervals": "Intervalli",
    "nav_sleep": "Sonno",
    "nav_breathe": "Respiro",
    "nav_stress": "Stress",
    "nav_workouts": "Allenamenti",
    "nav_trends": "Tendenze",
    "nav_coach": "Coach",
    "nav_insights_hub": "Cosa ti muove",
    "nav_insights": "Approfondimenti",
    "nav_explore": "Esplora",
    "nav_compare": "Confronta",
    "nav_health": "Salute",
    "nav_hydration": "Idratazione",
    "nav_vital_signs": "Segni vitali",
    "nav_lab_book": "Quaderno di laboratorio",
    "nav_rhythm": "Ritmo",
    "nav_apple_health": "Apple Health",
    "nav_automations": "Automazioni",
    "nav_alarms": "Sveglie",
    "nav_devices": "Dispositivi",
    "nav_noop_limitations": "Limiti di NOOP",
    "nav_data_sources": "Fonti dati",
    "nav_backup_sync": "Backup e sincronizzazione",
    "nav_fused_record": "I tuoi dati, uniti",
    "nav_notifications": "Notifiche",
    "nav_support": "Supporto",
    "nav_settings": "Impostazioni",
    "nav_test_centre": "Centro test",
    "nav_self_hosted_push": "Invio self-hosted",
    "nav_more": "Altro",
    "nav_power_saving": "Risparmio energetico",
    "more_group_insights": "Approfondimenti",
    "more_group_body": "Corpo",
    "more_group_data": "Dati",
    "more_group_app": "App",
    "sleep_status_calculating_title": "Calcolo del sonno di ieri notte…",
    "sleep_status_calculating_body": "La cronologia della fascia è arrivata. NOOP sta rilevando e analizzando la notte.",
    "sleep_status_sync_failed_title": "Il sonno di ieri notte non si è sincronizzato",
    "sleep_status_sync_failed_body": "La sincronizzazione della cronologia si è interrotta prima della fine. Tieni la fascia vicina e riprova Sincronizza.",
    "sleep_status_waiting_title": "In attesa del sonno di ieri notte",
    "sleep_status_waiting_body": "Collega la fascia e sincronizza la cronologia. NOOP calcolerà la notte quando arrivano i dati notturni.",
    "sleep_status_not_detected_title": "Il sonno di ieri notte non è stato rilevato",
    "sleep_status_not_detected_body": "La sincronizzazione è finita, ma NOOP non ha identificato con sicurezza una finestra di sonno. Tieni la fascia collegata e riprova Sincronizza; la notte precedente qui sotto resta l'ultimo sonno rilevato.",
    "terms_title": "Prima di usare NOOP",
    "terms_subtitle": "Leggi i punti qui sotto, poi conferma ogni affermazione.",
    "terms_point_independent_head": "Indipendente: non affiliato a WHOOP",
    "terms_point_independent_body": "NOOP è un progetto non ufficiale: non è affiliato, approvato o sponsorizzato da WHOOP, Inc. \"WHOOP\" è il loro marchio, usato solo per nominare l'hardware con cui NOOP funziona.",
    "terms_point_tos_head": "Usare NOOP può violare i Termini di servizio di WHOOP",
    "terms_point_tos_body": "Usalo solo con un dispositivo che possiedi, per leggere i tuoi dati. Se usarlo (e qualsiasi effetto su account WHOOP, abbonamento, dispositivo o garanzia) è una tua decisione, e un rischio solo tuo.",
    "terms_point_experimental_head": "Sperimentale: a tuo rischio",
    "terms_point_experimental_body": "NOOP parla con il firmware della fascia tramite un protocollo non ufficiale, mappato in modo indipendente. Resta un rischio residuo per il dispositivo, i suoi dati e il collegamento ai servizi ufficiali. Ti assumi quel rischio.",
    "terms_point_medical_head": "Non è un dispositivo medico, né un consiglio medico",
    "terms_point_medical_body": "Ogni metrica è un'approssimazione non validata. Non usare NOOP per diagnosticare, curare o prendere decisioni sulla salute. Consulta sempre un professionista qualificato.",
    "terms_point_warranty_head": "Nessuna garanzia; responsabilità limitata",
    "terms_point_warranty_body": "NOOP è gratuito e fornito \"così com'è\", senza garanzia. La responsabilità è limitata nella misura massima consentita dalla legge che ti riguarda, e nulla qui elimina tutele che la legge locale non permette di escludere.",
    "terms_footer": "I termini completi sono in TERMS.md, incluso con NOOP. Questo non è un parere legale.",
    "terms_attest_head": "Conferma ciascuno di questi punti:",
    "terms_attest_not_affiliated": "Non sono un dipendente, un collaboratore o un affiliato di WHOOP, e non sto usando NOOP per conto di WHOOP.",
    "terms_attest_own_device": "Possiedo il dispositivo WHOOP che userò con NOOP e lo userò solo per accedere ai miei dati. Farlo è una mia decisione e un mio rischio, incluso qualsiasi effetto su account WHOOP, abbonamento, dispositivo o garanzia, e può violare i Termini di servizio di WHOOP.",
    "terms_attest_asis": "Capisco che NOOP è non ufficiale e sperimentale, è fornito gratis e \"così com'è\" senza garanzia, e non è un dispositivo medico né un consiglio medico.",
    "terms_attest_liability": "Nella misura massima consentita dalla legge, non riterrò il progetto NOOP o chi vi contribuisce responsabile di perdite o danni derivanti dal mio uso.",
    "terms_checkbox": "Ho letto e accetto questi termini, e sto usando NOOP con il mio dispositivo e i miei dati, a mio rischio.",
    "terms_accept": "Accetta e continua",
    "trends_subtitle": "Il filo della tua storia nel tempo.",
    "onboarding_cta_begin": "Inizia",
    "onboarding_cta_continue": "Continua",
    "onboarding_cta_save_continue": "Salva e continua",
    "onboarding_cta_enter": "Entra in NOOP",
    "onboarding_three_promises": "Tre promesse, in silenzio.",
    "onboarding_recovery_body": "Un anello calmo riunisce HRV, frequenza cardiaca a riposo e sonno in una lettura: spingere o riposare.",
    "onboarding_live_hr_body": "Collega un WHOOP, una fascia cardio o un attrezzo in palestra e guarda ogni battito in tempo reale, con zone adatte al tuo profilo. Hai già una cronologia altrove? Importala da WHOOP, Apple Health, Oura, Fitbit o Garmin.",
    "onboarding_local_data_body": "Tutto resta su questo telefono. Nessun account, nessuna sincronizzazione, nessun cloud.",
    "onboarding_expectations_subtitle": "Qualche parola onesta, così niente è una sorpresa.",
    "onboarding_expectation_independent_body": "NOOP è un progetto personale e aperto: non è l'app WHOOP e non è affiliato a WHOOP. Legge una fascia che possiedi, sul tuo dispositivo. Trattalo come un lavoro capace ancora in corso, non come un prodotto finito.",
    "onboarding_expectation_whoop_support_body": "WHOOP 4.0 è collaudato e funziona dall'inizio alla fine. WHOOP 5.0/MG è più recente: la frequenza cardiaca dal vivo funziona già, ma le metriche più profonde (recupero, sforzo, sonno) per 5/MG sono ancora in definizione. NOOP ti dice sempre cosa è dal vivo e cosa è ancora in costruzione.",
    "onboarding_expectation_scores_body": "La frequenza cardiaca dal vivo è immediata. Recupero, sforzo e sonno si affinano mentre NOOP impara la tua base nelle prime notti di utilizzo. Vuoi la cronologia subito? Importa l'esportazione WHOOP in Fonti dati: il recupero richiede circa un minuto.",
    "onboarding_expectation_local_body": "Nessun account, nessun cloud, nessuna sincronizzazione. NOOP parla solo con la tua fascia e tiene tutto in locale. I tuoi dati sono solo tuoi.",
    "onboarding_bluetooth_subtitle": "NOOP usa il Bluetooth per trovare la fascia. Quando continui, consenti il permesso così può cercare.",
    "onboarding_bluetooth_local_body": "NOOP parla con la fascia direttamente via Bluetooth Low Energy. Non c'è un server in mezzo. Il collegamento è locale, e lo è ogni lettura che raccoglie.",
    "onboarding_bluetooth_permission": "Quando Android lo chiede, consenti il Bluetooth così NOOP può cercare e collegarsi.",
    "onboarding_whoop_pairing_mode": "WHOOP 5.0/MG può richiedere la modalità di associazione la prima volta, con l'app ufficiale WHOOP chiusa.",
    "onboarding_wear_subtitle": "Il sensore ha bisogno del contatto con la pelle prima che i dati significhino qualcosa.",
    "onboarding_wear_snug": "Indossala aderente al polso o al bicipite, sensore sulla pelle.",
    "onboarding_wear_charge": "Dalle qualche minuto di carica se la batteria è bassa.",
    "onboarding_wear_nearby": "Tienila vicino a questo telefono durante l'associazione e la prima sincronizzazione.",
    "onboarding_connect_bonded_subtitle": "Associata. Puoi continuare.",
    "onboarding_connect_searching_subtitle": "NOOP inizia a cercare appena compare questo passaggio. Puoi continuare mentre si associa.",
    "onboarding_connect_permission_subtitle": "Consenti il Bluetooth e tocca Cerca per trovare la fascia, oppure continua e collegala più tardi.",
    "onboarding_state_bonded_streaming": "Associata · in streaming",
    "onboarding_state_live_hr_unpaired": "FC dal vivo · non del tutto associata",
    "onboarding_state_connected_pairing": "Collegata · associazione",
    "onboarding_state_searching": "Ricerca",
    "onboarding_state_ready_scan": "Pronta per la ricerca",
    "onboarding_rescan": "Cerca di nuovo",
    "onboarding_connect_background_body": "Se la fascia è vicina, NOOP mantiene vivo il collegamento BLE in background. Puoi continuare con profilo e importazione mentre si associa.",
    "onboarding_strap_bonded_battery": "La fascia è associata · batteria %1$d%%.",
    "onboarding_strap_bonded_ready": "La fascia è associata e pronta per lo streaming.",
    "onboarding_profile_subtitle": "Così zone, calorie e punteggi sul dispositivo partono dai numeri giusti.",
    "onboarding_years": "anni",
    "onboarding_age_accessibility": "Età, %1$d anni",
    "onboarding_sex": "Sesso",
    "onboarding_male": "Uomo",
    "onboarding_female": "Donna",
    "onboarding_other": "Altro",
    "onboarding_units": "Unità",
    "onboarding_metric": "Metrico",
    "onboarding_imperial": "Imperiale",
    "onboarding_importing": "Importazione…",
    "onboarding_import_label": "Importa",
    "onboarding_failed": "non riuscita",
    "onboarding_health_connect_denied": "Accesso a Health Connect non concesso.",
    "onboarding_import_subtitle": "Facoltativo: importa ora, oppure salta e torna più tardi a Fonti dati.",
    "onboarding_import_history_body": "Un'esportazione WHOOP recupera recupero, sforzo, sonno e allenamenti. Health Connect può aggiungere passi, FC, HRV, sonno e peso da fonti Android.",
    "onboarding_notifications_subtitle": "NOOP tiene la fascia collegata in background. Quando continui, consenti le notifiche così può mostrare quel collegamento e raggiungere il polso.",
    "onboarding_notifications_status_body": "NOOP tiene aperto il collegamento Bluetooth in background così i dati restano aggiornati. Una notifica a bassa priorità mostra che è collegato. Niente di rumoroso.",
    "onboarding_notifications_alerts": "Anche gli avvisi al polso (solleciti di sforzo e la sveglia intelligente) arrivano come notifiche.",
    "onboarding_notifications_permission": "Quando Android lo chiede, consenti le notifiche così NOOP può tenerti informato.",
    "onboarding_appearance_subtitle": "NOOP segue il sistema per impostazione predefinita, oppure scegli Chiaro o Scuro. Puoi cambiarlo quando vuoi in Impostazioni → Aspetto.",
    "onboarding_system": "Sistema",
    "onboarding_theme_follow_system": "Segue l'impostazione chiaro/scuro del telefono.",
    "onboarding_theme_light_description": "Accento blu profondo su carta calda.",
    "onboarding_theme_dark_description": "Accento blu profondo su una tela blu-grigia scura.",
    "score_state_title_calibrating": "Calibrazione",
    "score_state_title_needs_strap": "Serve la fascia",
    "score_state_title_last_night": "Ieri notte · %1$s",
    "score_state_title_latest_sleep": "Ultimo sonno · %1$s",
    "score_state_detail_needs_strap": "Nessun dato per oggi. La fascia è stata indossata e collegata durante la notte?",
    "score_state_detail_carried_fresh": "Quello di stanotte arriva dopo che dormi con la fascia addosso.",
    "score_state_detail_carried_stale": "Questa è l'ultima sessione con un punteggio. Indossa la fascia di notte per un punteggio nuovo.",
    "settings_disclosure_expanded": "Espanso",
    "settings_disclosure_collapsed": "Compresso",
    "settings_streak_title": "Serie",
    "settings_language": "Lingua",
    "settings_choose_language": "Scegli la lingua",
    "settings_language_system": "Predefinita di sistema",
    "settings_appearance_detail": "Scegli Chiaro, Scuro, o segui il sistema. Scuro è il quasi-nero di firma; Chiaro mantiene lo stesso aspetto pulito su una tela luminosa.",
    "settings_theme_light": "Chiaro",
    "settings_theme_dark": "Scuro",
    "settings_chart_default": "Predefinito",
    "settings_chart_classic": "Classico",
    "settings_trend_line": "Linea",
    "settings_trend_bars": "Barre",
    "settings_waist_footnote_unset": "Facoltativo · il VO₂max si costruisce da circa 4 notti di frequenza cardiaca; il girovita lo rende più preciso. L'età fitness in sé non ne ha bisogno. Misura intorno alla vita, all'ombelico.",
    "settings_waist_footnote_set": "Il tuo VO₂max usa il girovita per una stima più precisa",
    "settings_day_cycle_title": "Ciclo del giorno",
    "settings_day_cycle_description": "Scegli quando passi e Sforzo in corso ricominciano. I pisolini non iniziano mai un nuovo giorno.",
    "settings_day_cycle_starts": "Il giorno inizia",
    "settings_day_cycle_sleep": "Sonno principale",
    "settings_day_cycle_midnight": "00:00",
    "settings_day_cycle_sleep_description": "Predefinito. Il ciclo segue l'inizio del sonno principale rilevato. Prima che venga rilevato, si usa la mezzanotte locale.",
    "settings_day_cycle_midnight_description": "Usa un giorno di calendario locale convenzionale, da 00:00 a 00:00.",
}

PLURAL_OVERRIDES: dict[str, dict[str, str]] = {
    "sync_chip_chunks_count": {
        "one": "%1$d blocco",
        "other": "%1$d blocchi",
    },
    "sync_chip_pages_behind_count": {
        "one": "%1$d pagina indietro alla connessione",
        "other": "%1$d pagine indietro alla connessione",
    },
    "settings_streak_run": {
        "one": "%1$d giorno di fila",
        "other": "%1$d giorni di fila",
    },
    "settings_streak_longest": {
        "one": "Record: %1$d giorno",
        "other": "Record: %1$d giorni",
    },
    "score_state_detail_calibrating": {
        "one": "Stiamo costruendo la tua base. Circa %1$d notte ancora prima che i punteggi siano personali.",
        "other": "Stiamo costruendo la tua base. Circa %1$d notti ancora prima che i punteggi siano personali.",
    },
    "alarm_countdown_days": {"one": "%1$d giorno", "other": "%1$d giorni"},
    "alarm_countdown_hours": {"one": "%1$d ora", "other": "%1$d ore"},
    "alarm_countdown_minutes": {"one": "%1$d minuto", "other": "%1$d minuti"},
}


def android_unescape(text: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            mapped = {"'": "'", '"': '"', "n": "\n", "t": "\t", "\\": "\\"}.get(nxt)
            if mapped is not None:
                out.append(mapped)
                i += 2
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def android_escape(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace("\n", "\\n")
    text = text.replace("\t", "\\t")
    text = text.replace("'", "\\'")
    text = text.replace('"', '\\"')
    return text


def signature(value: str) -> list[str]:
    return sorted(SPEC_RE.findall(value))


def shield(text: str) -> tuple[str, list[str]]:
    tokens: list[str] = []

    def repl(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"QZF{len(tokens) - 1}"

    return SPEC_RE.sub(repl, text), tokens


def apply_glossary(text: str) -> str:
    for pattern, replacement in INLINE_TERMS:
        text = re.sub(pattern, replacement, text)
    for source, token, _italian in BRANDS:
        text = text.replace(source, token)
    return text


def restore_glossary(text: str) -> str:
    for _source, token, italian in sorted(BRANDS, key=lambda row: -len(row[1])):
        text = re.sub(re.escape(token), italian, text, flags=re.IGNORECASE)
    return text


def polish_italian(text: str) -> str:
    """Strap wording and a few systematic mistranslations.

    Google alternates between «cinturino» and «fascia». This fork uses fascia,
    which is how the band is referred to in Italian. Articles are rewritten
    with the phrase so gender stays correct (il cinturino → la fascia).
    """
    replacements = [
        (r"\bdei cinturini\b", "delle fasce"),
        (r"\bdei Cinturini\b", "delle fasce"),
        (r"\bdel cinturino\b", "della fascia"),
        (r"\bDel cinturino\b", "Della fascia"),
        (r"\bal cinturino\b", "alla fascia"),
        (r"\bdal cinturino\b", "dalla fascia"),
        (r"\bsul cinturino\b", "sulla fascia"),
        (r"\bnel cinturino\b", "nella fascia"),
        (r"\bil tuo cinturino\b", "la tua fascia"),
        (r"\bIl tuo cinturino\b", "La tua fascia"),
        (r"\bil cinturino\b", "la fascia"),
        (r"\bIl cinturino\b", "La fascia"),
        (r"\bun cinturino\b", "una fascia"),
        (r"\bUn cinturino\b", "Una fascia"),
        (r"\bi cinturini\b", "le fasce"),
        (r"\bI cinturini\b", "Le fasce"),
        (r"\bquesto cinturino\b", "questa fascia"),
        (r"\bQuesto cinturino\b", "Questa fascia"),
        (r"\bcinturini\b", "fasce"),
        (r"\bCinturini\b", "Fasce"),
        (r"\bcinturino\b", "fascia"),
        (r"\bCinturino\b", "Fascia"),
        (r"\bla cinghia\b", "la fascia"),
        (r"\bLa cinghia\b", "La fascia"),
        (r"\bdella cinghia\b", "della fascia"),
        (r"\bcinghie\b", "fasce"),
        (r"\bcinghia\b", "fascia"),
        (r"\bCinghia\b", "Fascia"),
        # "Charge" left as a billing term when the token path missed it.
        (r"\bAddebito\b", "Carica"),
        (r"\baddebito\b", "carica"),
        (r"\bSottoporre a tensione\b", "Sforzo"),
        (r"\bsottoporre a tensione\b", "sforzo"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return text


def restore_specs(text: str, tokens: list[str]) -> str | None:
    for i, spec in enumerate(tokens):
        pattern = re.compile(rf"QZF\s*{i}", re.IGNORECASE)
        if not pattern.search(text):
            return None
        text = pattern.sub(spec, text, count=1)
    if re.search(r"QZF\s*\d", text, re.IGNORECASE):
        return None
    return text


def translate_google(text: str) -> str:
    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=it&dt=t&q="
        + urllib.parse.quote(text)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                data = json.loads(response.read().decode())
            return "".join(part[0] for part in data[0] if part[0])
        except Exception as exc:  # noqa: BLE001 — retry network and HTTP errors
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"translate failed: {last_error}")


def translate_many(texts: list[str], cache: dict[str, str]) -> list[str]:
    pending = [t for t in texts if t not in cache]
    delim = "\nQZSPLIT\n"
    batch: list[str] = []
    budget = 0
    batches: list[list[str]] = []
    for text in pending:
        if batch and budget + len(text) + len(delim) > 3500:
            batches.append(batch)
            batch = []
            budget = 0
        batch.append(text)
        budget += len(text) + len(delim)
    if batch:
        batches.append(batch)

    def commit(originals: list[str], translated: list[str]) -> None:
        if len(originals) != len(translated):
            raise RuntimeError("batch size mismatch")
        for src, dst in zip(originals, translated):
            cache[src] = dst

    def run_batch(originals: list[str]) -> None:
        if len(originals) == 1:
            cache[originals[0]] = translate_google(originals[0])
            return
        joined = delim.join(originals)
        out = translate_google(joined)
        parts = re.split(r"\s*QZSPLIT\s*", out.strip())
        if len(parts) != len(originals):
            mid = len(originals) // 2
            run_batch(originals[:mid])
            run_batch(originals[mid:])
            return
        commit(originals, [p.strip() for p in parts])

    for index, originals in enumerate(batches, start=1):
        run_batch(originals)
        if index % 10 == 0:
            print(f"  translated batch {index}/{len(batches)}", flush=True)
        time.sleep(0.15)
    return [cache[t] for t in texts]


def prepare(english: str) -> tuple[str, list[str], str, str]:
    """Return shielded text, format tokens, leading quote-space, trailing quote-space.

    Resources wrapped in literal double quotes keep edge whitespace that AAPT
    would otherwise trim. The quotes are part of the XML text, not XML syntax.
    """
    raw = android_unescape(english)
    prefix = ""
    suffix = ""
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        inner = raw[1:-1]
        lead = len(inner) - len(inner.lstrip(" "))
        trail = len(inner) - len(inner.rstrip(" "))
        prefix = '"' + (" " * lead)
        suffix = (" " * trail) + '"'
        raw = inner.strip(" ")
    shielded, tokens = shield(raw)
    return apply_glossary(shielded), tokens, prefix, suffix


def finalize(translated: str, tokens: list[str], prefix: str, suffix: str) -> str | None:
    restored = restore_specs(translated, tokens)
    if restored is None:
        return None
    restored = restore_glossary(restored)
    restored = polish_italian(restored)
    restored = restored.strip()
    if prefix or suffix:
        # prefix/suffix already include the wrapping quotes and edge spaces.
        inner_lead = prefix[1:]
        inner_trail = suffix[:-1]
        restored = '"' + inner_lead + restored.strip() + inner_trail + '"'
    return restored


def load_cache() -> dict[str, str]:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict[str, str]) -> None:
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def existing_translations() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    strings: dict[str, str] = {}
    plurals: dict[str, dict[str, str]] = {}
    if not OUT.exists():
        return strings, plurals
    root = ET.parse(OUT).getroot()
    for node in root.findall("string"):
        strings[node.attrib["name"]] = node.text or ""
    for node in root.findall("plurals"):
        plurals[node.attrib["name"]] = {
            item.attrib["quantity"]: item.text or "" for item in node.findall("item")
        }
    return strings, plurals


def translate_value(english_xml: str, cache: dict[str, str], strict: bool) -> str:
    shielded, tokens, prefix, suffix = prepare(english_xml)
    if not re.search(r"[A-Za-z]", android_unescape(english_xml)):
        return english_xml
    if shielded not in cache:
        try:
            translate_many([shielded], cache)
        except Exception as exc:  # noqa: BLE001
            print(f"  translate error: {exc}")
            if strict:
                raise
            return english_xml
    done = finalize(cache[shielded], tokens, prefix, suffix)
    if done is None or signature(android_unescape(done)) != signature(android_unescape(english_xml)):
        # One isolated retry, then keep English rather than ship a broken format.
        try:
            cache[shielded] = translate_google(shielded)
            save_cache(cache)
        except Exception:
            return english_xml
        done = finalize(cache[shielded], tokens, prefix, suffix)
        if done is None or signature(android_unescape(done)) != signature(android_unescape(english_xml)):
            return english_xml
    return android_escape(done) if not done.startswith('"') else _escape_quoted(done)


def _escape_quoted(quoted: str) -> str:
    """Escape an already-quoted resource without escaping the wrapping quotes' meaning.

    The wrapping quotes are literal characters AAPT uses to preserve edge spaces.
    Apostrophes inside still need Android escapes; the wrapping quotes stay.
    """
    assert quoted[0] == '"' and quoted[-1] == '"'
    inner = quoted[1:-1]
    inner = inner.replace("&", "&amp;").replace("<", "&lt;")
    inner = inner.replace("'", "\\'")
    return '"' + inner + '"'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="regenerate every key, ignoring existing Italian")
    parser.add_argument("--strict", action="store_true", help="fail if a key cannot be translated")
    args = parser.parse_args()

    base = ET.parse(BASE).getroot()
    have_strings, have_plurals = existing_translations()
    cache = load_cache()

    # Warm the cache for everything that still needs a translation.
    needed: list[str] = []
    jobs: list[tuple[str, str]] = []
    for node in base:
        if node.tag == "string":
            name = node.attrib["name"]
            if name in OVERRIDES or (not args.force and name in have_strings):
                continue
            if node.attrib.get("translatable") == "false":
                continue
            english = node.text or ""
            shielded, _tokens, _prefix, _suffix = prepare(english)
            if re.search(r"[A-Za-z]", android_unescape(english)) and shielded not in cache:
                needed.append(shielded)
            jobs.append((name, english))
        elif node.tag == "plurals":
            name = node.attrib["name"]
            if name in PLURAL_OVERRIDES or (not args.force and name in have_plurals):
                continue
            for item in node.findall("item"):
                english = item.text or ""
                shielded, _tokens, _prefix, _suffix = prepare(english)
                if shielded not in cache:
                    needed.append(shielded)
    # Dedupe needed while preserving order.
    seen: set[str] = set()
    unique = []
    for text in needed:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    print(f"translating {len(unique)} unique strings ({len(jobs)} resource keys pending)")
    if unique:
        translate_many(unique, cache)
        save_cache(cache)

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!--",
        "  Italian UI for the FlipUp fork (values-it). Hand-written overrides cover",
        "  navigation, onboarding, and terms; the remaining keys are translated from",
        "  values/strings.xml. Code identifiers stay English. Android falls back to",
        "  values/ when a key is missing, so a partial file still runs.",
        "-->",
        "<resources>",
    ]
    kept_english = 0
    for node in base:
        if node.tag == "string":
            name = node.attrib["name"]
            attrs = ""
            if node.attrib.get("translatable") == "false":
                attrs = ' translatable="false"'
                value = android_escape(android_unescape(node.text or ""))
            elif name in OVERRIDES and (args.force or name not in have_strings or True):
                # Overrides are the fork's curated copy. Always apply them so a
                # bad machine string cannot shadow a hand translation. Existing
                # file values are kept only when --force is off AND the key is
                # not in the override table (handled below).
                value = android_escape(OVERRIDES[name]) if not OVERRIDES[name].startswith('"') else _escape_quoted(OVERRIDES[name])
                # android_escape turns the override's plain apostrophes into \'.
                # Overrides are plain Italian, not pre-escaped.
            elif not args.force and name in have_strings:
                value = have_strings[name]
                # have_strings came through ElementTree, so escapes are already
                # decoded. Re-escape for the file.
                value = android_escape(value) if not (value.startswith('"') and value.endswith('"')) else _escape_quoted(value)
            else:
                english = node.text or ""
                translated = translate_value(english, cache, args.strict)
                if translated == english or android_unescape(translated) == android_unescape(english):
                    if re.search(r"[A-Za-z]{3,}", android_unescape(english)):
                        kept_english += 1
                value = translated if translated != english else android_escape(android_unescape(english))
            lines.append(f'    <string name="{name}"{attrs}>{value}</string>')
        elif node.tag == "plurals":
            name = node.attrib["name"]
            lines.append(f'    <plurals name="{name}">')
            override = PLURAL_OVERRIDES.get(name)
            existing = have_plurals.get(name)
            for item in node.findall("item"):
                qty = item.attrib["quantity"]
                if override and qty in override:
                    value = android_escape(override[qty])
                elif not args.force and existing and qty in existing:
                    raw = existing[qty]
                    value = android_escape(raw) if not (raw.startswith('"') and raw.endswith('"')) else _escape_quoted(raw)
                else:
                    value = translate_value(item.text or "", cache, args.strict)
                lines.append(f'        <item quantity="{qty}">{value}</item>')
            lines.append("    </plurals>")
    lines.append("</resources>")
    lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    save_cache(cache)
    print(f"wrote {OUT} ({kept_english} keys left in English)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
