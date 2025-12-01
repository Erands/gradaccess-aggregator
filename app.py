from flask import Flask, request, jsonify
import os, requests, io, csv

app = Flask(__name__)

# Load keys from environment EXACTLY as Railway provides
AGG_SECRET = os.environ.get("AGG_SECRET", "changeme")
DATA_GOV_KEY = os.environ.get("DATA_GOV_KEY", "2vNIhXFeb9d2TH0ebiJ0GVVDJX5lof06jftXuXqR")

print("==========================================")
print("🔍 DEBUG: AGG_SECRET =", AGG_SECRET)
print("🔍 DEBUG: DATA_GOV_KEY =", DATA_GOV_KEY)
print("==========================================")


# Optional: per-country CSV or API URLs (can be set as env VARS like SRC_UK_CSV)
SOURCES = {
    'UK': os.environ.get('SRC_UK_CSV', 'https://discoveruni.gov.uk/static/data/csv/all-institutions.csv'),
    'NORWAY': os.environ.get('SRC_NORWAY_CSV', ''),   # provide CSV URL in env
    'AUSTRALIA': os.environ.get('SRC_AUSTRALIA_CSV', ''),  # CRICOS / TEQSA CSV
    'CANADA': os.environ.get('SRC_CANADA_CSV', ''),   # provincial CSV or dataset
    'GERMANY': os.environ.get('SRC_GERMANY_CSV', ''),
    'FRANCE': os.environ.get('SRC_FRANCE_CSV', ''),
    'LUXEMBOURG': os.environ.get('SRC_LUX_CSV', ''),
    'NEWZEALAND': os.environ.get('SRC_NZ_CSV', ''),
    'FINLAND': os.environ.get('SRC_FINLAND_CSV', ''),
    'JAPAN': os.environ.get('SRC_JAPAN_CSV', ''),
    'SINGAPORE': os.environ.get('SRC_SG_CSV', ''),
    'CHINA': os.environ.get('SRC_CHINA_CSV', ''),
}

# Utility functions
def unauthorized():
    return jsonify({'error': 'unauthorized'}), 403

def fetch_json(url, params=None, headers=None, timeout=30):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {'_error': str(e)}

def fetch_text(url, params=None, headers=None, timeout=30):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return None

# Top-level programs endpoint
@app.route('/api/v1/programs')
def programs():
    secret = request.headers.get('X-GA-SECRET') or request.args.get('secret')
    if secret != AGG_SECRET:
        return unauthorized()

    country = (request.args.get('country') or 'ALL').upper()
    page = int(request.args.get('page') or 1)
    per_page = int(request.args.get('per_page') or 100)

    # Dispatch
    if country == 'US' or country == 'ALL':
        return jsonify(fetch_scorecard(page, per_page))
    if country == 'UK':
        return jsonify(fetch_discoveruni(page, per_page))
    if country == 'NORWAY':
        return jsonify(fetch_csv_source('NORWAY', page, per_page))
    if country == 'AUSTRALIA':
        return jsonify(fetch_csv_source('AUSTRALIA', page, per_page))
    if country == 'NEWZEALAND':
        return jsonify(fetch_csv_source('NEWZEALAND', page, per_page))
    if country == 'FINLAND':
        return jsonify(fetch_csv_source('FINLAND', page, per_page))
    if country == 'JAPAN':
        return jsonify(fetch_csv_source('JAPAN', page, per_page))
    if country == 'SINGAPORE':
        return jsonify(fetch_csv_source('SINGAPORE', page, per_page))
    if country == 'CHINA':
        return jsonify(fetch_csv_source('CHINA', page, per_page))
    if country == 'CANADA':
        return jsonify(fetch_csv_source('CANADA', page, per_page))
    if country == 'GERMANY':
        return jsonify(fetch_csv_source('GERMANY', page, per_page))
    if country == 'FRANCE':
        return jsonify(fetch_csv_source('FRANCE', page, per_page))
    if country == 'LUXEMBOURG':
        return jsonify(fetch_csv_source('LUXEMBOURG', page, per_page))

    # All: combine a couple of fast sources (US + UK)
    out_us = fetch_scorecard(page, per_page)
    out_uk = fetch_discoveruni(page, per_page)
    combined = out_us.get('programs', []) + out_uk.get('programs', [])
    return jsonify({'programs': combined, 'meta': {'page': 1, 'count': len(combined)}})

# ---------------------------
# Connectors
# ---------------------------

def fetch_scorecard(page=1, per_page=100):
    if not DATA_GOV_KEY:
        return {'programs': [], 'meta': {'error': 'no_data_gov_key'}}

    url = "https://api.data.gov/ed/collegescorecard/v1/schools.json"

    params = {
        "api_key": DATA_GOV_KEY,
        "fields": "id,school.name,school.city,school.state,latest.cost.tuition.in_state,latest.cost.tuition.out_of_state",
        "per_page": per_page,
        "page": page - 1
    }

    print("DEBUG: Calling Scorecard API with:", params)

    j = fetch_json(url, params=params)

    if not isinstance(j, dict) or "results" not in j:
        return {"programs": [], "meta": {"error": "scorecard_fetch_failed", "raw": j}}

    programs = []

    for item in j["results"]:
        # Extract fields using flat keys
        name = item.get("school.name")
        city = item.get("school.city")
        state = item.get("school.state")

        tuition = (
            item.get("latest.cost.tuition.out_of_state")
            or item.get("latest.cost.tuition.in_state")
        )

        programs.append({
            "name": f"{name} (various programs)" if name else "Unknown School",
            "institution": name,
            "degree_level": "all",
            "tuition_amount": tuition,
            "tuition_currency": "USD",
            "country": "US",
            "city": city or state,
            "source": "scorecard",
            "source_id": str(item.get("id")),
        })

    return {
        "programs": programs,
        "meta": {
            "page": page,
            "count": len(programs),
            "more": len(programs) == per_page
        }
    }

def fetch_discoveruni(page=1, per_page=100):
    """DiscoverUni (UK) full-institutions CSV (institution-level)."""
    csv_url = SOURCES.get('UK')
    if not csv_url:
        return {'programs': [], 'meta': {'error': 'no_uk_csv_configured'}}
    txt = fetch_text(csv_url)
    if not txt:
        return {'programs': [], 'meta': {'error': 'discoveruni_fetch_failed'}}
    f = io.StringIO(txt)
    reader = csv.DictReader(f)
    rows = list(reader)
    start = (page-1)*per_page
    slice_rows = rows[start:start+per_page]
    out = []
    for r in slice_rows:
        out.append({
            'name': r.get('name') or r.get('institution') or (r.get('country') or 'UK Institution'),
            'institution': r.get('name') or r.get('institution'),
            'degree_level': 'all',
            'tuition_amount': None,
            'tuition_currency': 'GBP',
            'country': 'GB',
            'city': r.get('city') or '',
            'source': 'discoveruni',
            'source_id': r.get('ukprn') or r.get('id')
        })
    return {'programs': out, 'meta': {'page': page, 'count': len(out), 'more': start+per_page < len(rows)}}

def fetch_csv_source(country_key, page=1, per_page=100):
    """Generic CSV source loader: expects a CSV with at least name/institution columns.
       You must set SOURCES['COUNTRYKEY'] to a CSV URL (env var recommended).
    """
    csv_url = SOURCES.get(country_key, '')
    if not csv_url:
        return {'programs': [], 'meta': {'error': f'no_{country_key.lower()}_csv_configured'}}

    txt = fetch_text(csv_url)
    if not txt:
        return {'programs': [], 'meta': {'error': f'{country_key}_fetch_failed'}}

    f = io.StringIO(txt)
    reader = csv.DictReader(f)
    rows = list(reader)
    start = (page-1)*per_page
    slice_rows = rows[start:start+per_page]
    out = []
    for r in slice_rows:
        # heuristics to find useful fields
        name = r.get('program_name') or r.get('name') or r.get('course') or r.get('title') or r.get('institution') or r.get('school')
        inst = r.get('institution') or r.get('school') or r.get('provider') or ''
        country = r.get('country') or country_key[:2]
        tuition = None
        if 'tuition' in r and r.get('tuition'):
            try:
                tuition = float(r.get('tuition'))
            except:
                tuition = None
        out.append({
            'name': name if name else (inst + ' (various programs)'),
            'institution': inst,
            'degree_level': r.get('degree_level') or 'all',
            'tuition_amount': tuition,
            'tuition_currency': r.get('tuition_currency') or None,
            'country': country,
            'city': r.get('city') or '',
            'source': country_key.lower(),
            'source_id': r.get('id') or r.get('ukprn') or ''
        })
    return {'programs': out, 'meta': {'page': page, 'count': len(out), 'more': start+per_page < len(rows)}}

# Running the app
if __name__ == '__main__':
    # honor Render/host PORT env var
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
