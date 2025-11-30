from flask import Flask, request, jsonify
import os, requests, io, csv

app = Flask(__name__)

# ------------------------------
# HARD-CODED API KEY (your key)
# ------------------------------
AGG_SECRET = "changeme"
DATA_GOV_KEY = "2vNIhXFeb9d2TH0ebiJ0GVVDJX5lof06jftXuXqR"
# ------------------------------

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

@app.route('/api/v1/programs')
def programs():
    secret = request.headers.get('X-GA-SECRET') or request.args.get('secret')
    if secret != AGG_SECRET:
        return unauthorized()

    country = (request.args.get('country') or 'ALL').upper()
    page = int(request.args.get('page') or 1)
    per_page = int(request.args.get('per_page') or 100)

    if country == 'US' or country == 'ALL':
        return jsonify(fetch_scorecard(page, per_page))

    if country == 'UK':
        return jsonify(fetch_discoveruni(page, per_page))

    # Default for unimplemented countries
    return jsonify({'programs': [], 'meta': {'note': 'country placeholder'}})

def fetch_scorecard(page=1, per_page=100):
    if not DATA_GOV_KEY:
        return {'programs': [], 'meta': {'error': 'no_data_gov_key'}}

    base = 'https://api.data.gov/ed/collegescorecard/v1/schools.json'
    params = {
        'api_key': DATA_GOV_KEY,
        'fields': 'id,school.name,school.city,school.state,latest.cost.tuition.out_of_state,latest.cost.tuition.in_state',
        'per_page': per_page,
        'page': page - 1
    }

    j = fetch_json(base, params=params)

    if not isinstance(j, dict) or 'results' not in j:
        return {'programs': [], 'meta': {'error': 'scorecard_fetch_failed'}}

    progs = []

    for item in j.get('results', []):
        name = item.get('school', {}).get('name')
        city = item.get('school', {}).get('city')
        state = item.get('school', {}).get('state')

        tuition = None
        try:
            tuition = item['latest']['cost']['tuition'].get('out_of_state') \
                or item['latest']['cost']['tuition'].get('in_state')
        except:
            tuition = None

        progs.append({
            'name': (name or 'Unknown') + ' (various programs)',
            'institution': name,
            'degree_level': 'all',
            'tuition_amount': tuition,
            'tuition_currency': 'USD',
            'country': 'US',
            'city': city,
            'source': 'scorecard',
            'source_id': str(item.get('id'))
        })

    return {
        'programs': progs,
        'meta': {
            'page': page,
            'count': len(progs),
            'more': False
        }
    }

def fetch_discoveruni(page=1, per_page=100):
    csv_url = 'https://discoveruni.gov.uk/static/data/csv/all-institutions.csv'
    txt = fetch_text(csv_url)

    if not txt:
        return {'programs': [], 'meta': {'note': 'discoveruni CSV not available'}}

    f = io.StringIO(txt)
    reader = csv.DictReader(f)
    rows = list(reader)

    start = (page - 1) * per_page
    slice_rows = rows[start:start + per_page]

    out = []
    for r in slice_rows:
        out.append({
            'name': r.get('name') or r.get('institution'),
            'institution': r.get('name'),
            'degree_level': 'all',
            'tuition_amount': None,
            'tuition_currency': 'GBP',
            'country': 'GB',
            'source': 'discoveruni',
            'source_id': r.get('ukprn') or r.get('id')
        })

    return {
        'programs': out,
        'meta': {
            'page': page,
            'count': len(out),
            'more': start + per_page < len(rows)
        }
    }

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
