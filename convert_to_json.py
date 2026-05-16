import json
import math
import os
import hashlib
import unicodedata
from datetime import datetime
from pathlib import Path

import pandas as pd

# Configuration de sécurité
WORKING_DIR = Path(os.environ.get('BOOKVERRES_SOURCE_DIR', 'data/sources/current'))
CATALOGS_DIR = Path('catalogs')
CANDIDATES_DIR = CATALOGS_DIR / 'candidates'
PUBLISHED_DIR = CATALOGS_DIR / 'published'
ARCHIVE_DIR = CATALOGS_DIR / 'archive'
REPORT_JSON = Path('generation_report.json')

REQUIRED_NETWORKS = [
    'Carte Blanche',
    'Kalixia',
    'Optilys',
    'Santeclair',
    'Seveane',
]
OPTIONAL_NETWORKS = [
    'Itelis',
    'Actil',
]
NETWORKS = REQUIRED_NETWORKS + OPTIONAL_NETWORKS

NETWORK_ALIASES = {
    'Carte Blanche': ['carte blanche', 'carteblanche'],
    'Kalixia': ['kalixia', 'kalikia'],
    'Optilys': ['optilys'],
    'Santeclair': ['santeclair', 'sante clair', 'santéclair', 'santeClair'],
    'Seveane': ['seveane', 'sévéane'],
    'Itelis': ['itelis'],
    'Actil': ['actil'],
}

TARGET_KEYS = [
    'code_EDI',
    'Code Fabricant',
    'Marque',
    'Libelle',
    'Indice',
    'Geometrie',
    'Type',
    'Verres Spéciaux',
    'Modele Verrier',
    'Modele MDD',
    'Traitement Verrier',
    'Traitement MDD',
    'STOCK / RX',
    'TT OU NON TT',
    'OPTION\nVerrier',
    'OPTION\nMDD',
    'OPTION\nMIROIR',
    'OPTION\nDEGRADE',
    'OPTION\nUVBLS',
    'OPTION\nPROTECTUV',
    'OPTION\nANTIBUEE',
    'OPTION\nSANSEQUIVALENCE',
    'LIBELLE CHAPEAU',
    'PVP',
    'Prix Achat Brut',
    'Prix Achat Net',
    '% TOTAL REMISE',
    'Net forcé',
    'P2 MDD',
    'Verre supprimé',
    'Date Suppression',
    'prix_reseau',
]

NETWORK_RANGE_KEYS = [
    'sphère debut',
    'sphère fin',
    'Cylindre début',
    'Cylindre fin',
    'PVP TTC',
]

REQUIRED_PRODUCT_NUMERIC_FIELDS = [
    'PVP',
    'Prix Achat Net',
]

CSV_COLUMNS = [
    'Libelle',
    'Code EDI',
    'x',
    'Sphere debut',
    'Sphere fin',
    'Cylindre debut',
    'Cylindre fin',
    'PVP TTC',
]

REQUIRED_PAO_COLUMNS = ['Code EDI']
REPORT_SAMPLE_LIMIT = 50
WITHOUT_PRICE_ANALYSIS_FIELDS = [
    'code_EDI',
    'Libelle',
    'Indice',
    'Geometrie',
    'Type',
    'Modele Verrier',
    'Modele MDD',
    'Traitement Verrier',
    'Traitement MDD',
    'STOCK / RX',
    'Verre supprimé',
    'Date Suppression',
    'PVP',
    'Prix Achat Net',
]
WITHOUT_PRICE_GROUP_FIELDS = [
    'Geometrie',
    'Type',
    'Modele Verrier',
    'Modele MDD',
    'Traitement Verrier',
    'STOCK / RX',
    'Verre supprimé',
    'Date Suppression',
]
EDI_DIAGNOSTIC_MODEL_KEYWORDS = [
    'JETSTAR',
    'SENSO',
    'SEIKO INDI-SV',
    'SMARTZOOM',
]


class GenerationError(Exception):
    pass


def ensure_catalog_dirs():
    for path in (CANDIDATES_DIR, PUBLISHED_DIR, ARCHIVE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def build_candidate_context():
    generated_at = datetime.now().astimezone()
    timestamp = generated_at.strftime('%Y-%m-%d_%H-%M')
    filename = f'verres_complet_candidate_{timestamp}.json'
    return {
        'generated_at': generated_at.isoformat(timespec='seconds'),
        'generated_filename': filename,
        'output_json': CANDIDATES_DIR / filename,
    }


def new_report(context):
    return {
        'status': 'running',
        'generated_filename': context['generated_filename'],
        'generated_at': context['generated_at'],
        'catalog_version': context['generated_filename'].replace('verres_complet_candidate_', '').replace('.json', ''),
        'sha256': None,
        'errors': [],
        'warnings': [],
        'config': {
            'required_networks': REQUIRED_NETWORKS,
            'optional_networks': OPTIONAL_NETWORKS,
            'networks': NETWORKS,
            'target_keys_count': len(TARGET_KEYS),
            'network_range_keys': NETWORK_RANGE_KEYS,
        },
        'files': {
            'working_dir': str(WORKING_DIR),
            'pao_file': None,
            'csv_files': {},
            'output_json': str(context['output_json']),
            'report_json': str(REPORT_JSON),
        },
        'input_files': {
            'pao': None,
            'required_networks': {},
            'optional_networks': {},
        },
        'metrics': {
            'total_pao_products': 0,
            'generated_products': 0,
            'detected_networks': [],
            'missing_required_networks': [],
            'missing_optional_networks': [],
            'products_with_at_least_one_network_price': 0,
            'products_without_any_network_price': 0,
            'products_without_any_network_price_ratio': 0,
            'products_priced_by_network': {network: 0 for network in NETWORKS},
            'csv_rows_by_network': {network: 0 for network in NETWORKS},
            'csv_matched_codes_by_network': {network: 0 for network in NETWORKS},
            'csv_orphan_codes_by_network': {network: 0 for network in NETWORKS},
            'empty_required_networks': [],
            'empty_optional_networks': [],
        },
        'network_analysis': {
            'csv_rows_by_network': {network: 0 for network in NETWORKS},
            'matched_codes': {network: 0 for network in NETWORKS},
            'orphan_codes': {network: 0 for network in NETWORKS},
            'empty_networks': [],
        },
        'samples': {
            'pao_codes_without_price': [],
            'csv_orphan_codes': {network: [] for network in NETWORKS},
        },
        'products_without_any_network_price_analysis': {
            'total': 0,
            'sample_limit': REPORT_SAMPLE_LIMIT,
            'sample': [],
            'groupings': {},
            'classification': {},
            'recommendation': None,
            'edi_diagnostic': {},
        },
        'hors_reseau_uniquement': {
            'count': 0,
            'samples': [],
            'groupings': {},
        },
    }


def add_error(report, message):
    report['errors'].append(message)


def add_warning(report, message):
    report['warnings'].append(message)


def write_report(report):
    with REPORT_JSON.open('w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)


def fail(report, message=None):
    if message:
        add_error(report, message)
    report['status'] = 'failed'
    output_json = Path(report['files']['output_json'])
    if output_json.exists():
        output_json.unlink()
    write_report(report)
    raise GenerationError(message or 'Generation failed')


def clean_scalar(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def clean_string(value, default=''):
    value = clean_scalar(value)
    if value is None:
        return default
    return str(value).strip()


def finite_number(value, context):
    value = clean_scalar(value)
    if value is None or value == '':
        raise ValueError(f'{context}: valeur absente')
    if isinstance(value, str):
        value = value.strip().replace(',', '.')
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f'{context}: valeur non finie')
    return number


def finite_catalog_number(value, context):
    value = clean_scalar(value)
    if value is None:
        raise ValueError(f'{context}: valeur absente')
    text = str(value).strip()
    if not text:
        raise ValueError(f'{context}: valeur absente')
    text = text.replace('\u00a0', ' ').replace('€', '').replace(' ', '').replace(',', '.')
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f'{context}: valeur non finie')
    return number


def normalize_network_token(value):
    text = str(value).lower()
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return ''.join(ch for ch in text if ch.isalnum())


def file_matches_network(path, network):
    file_token = normalize_network_token(path.stem)
    aliases = NETWORK_ALIASES.get(network, [network])
    return any(normalize_network_token(alias) in file_token for alias in aliases)


def find_pao_file(report):
    if not WORKING_DIR.exists() or not WORKING_DIR.is_dir():
        fail(report, f'Dossier de travail introuvable: {WORKING_DIR}')

    matches = [
        path for path in WORKING_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in ('.xlsx', '.xls')
        and ('pao_sei' in path.name.lower() or 'paoseiko' in path.name.lower() or 'pao_seiko' in path.name.lower())
        and not path.name.startswith('~$')
    ]
    if not matches:
        fail(report, 'Aucun fichier PAO_SEI / PAOSEIKO .xlsx/.xls trouvé.')
    if len(matches) > 1:
        fail(report, f'Plusieurs fichiers PAO_SEI détectés: {[p.name for p in matches]}')

    report['files']['pao_file'] = str(matches[0])
    report['input_files']['pao'] = str(matches[0])
    return matches[0]


def find_csv_files(report):
    csv_files = {}
    missing_required = []
    missing_optional = []
    for network in NETWORKS:
        matches = [
            path for path in WORKING_DIR.iterdir()
            if path.is_file()
            and path.suffix.lower() == '.csv'
            and file_matches_network(path, network)
        ]
        if not matches:
            if network in OPTIONAL_NETWORKS:
                missing_optional.append(network)
                add_warning(report, f'Fichier réseau optionnel absent: {network}')
            else:
                missing_required.append(network)
                add_error(report, f'Fichier réseau obligatoire absent: {network}')
            continue
        if len(matches) > 1:
            add_error(report, f'Plusieurs CSV détectés pour {network}: {[p.name for p in matches]}')
            continue
        csv_files[network] = matches[0]
        report['files']['csv_files'][network] = str(matches[0])
        bucket = 'optional_networks' if network in OPTIONAL_NETWORKS else 'required_networks'
        report['input_files'][bucket][network] = str(matches[0])

    report['metrics']['detected_networks'] = sorted(csv_files.keys())
    report['metrics']['missing_required_networks'] = missing_required
    report['metrics']['missing_optional_networks'] = missing_optional
    return csv_files


def prepare_pao_dataframe(report, pao_file):
    try:
        pao_df = pd.read_excel(pao_file)
    except Exception as exc:
        fail(report, f'Lecture PAO impossible ({pao_file.name}): {exc}')

    original_columns = list(pao_df.columns)
    clean_columns = [str(col).strip().replace('\n', ' ') for col in pao_df.columns]
    pao_df.columns = clean_columns

    missing = [col for col in REQUIRED_PAO_COLUMNS if col not in clean_columns]
    if missing:
        fail(report, f'Colonnes PAO obligatoires absentes: {missing}')

    pao_df['Code EDI'] = pao_df['Code EDI'].apply(lambda value: clean_string(value))
    pao_df = pao_df[pao_df['Code EDI'] != '']
    report['metrics']['total_pao_products'] = int(len(pao_df))

    if pao_df.empty:
        fail(report, 'Aucun verre PAO exploitable après nettoyage des codes EDI.')

    duplicate_codes = sorted(pao_df[pao_df['Code EDI'].duplicated()]['Code EDI'].unique().tolist())
    if duplicate_codes:
        fail(report, f'Codes EDI dupliqués dans le PAO: {duplicate_codes[:REPORT_SAMPLE_LIMIT]}')

    return pao_df, original_columns, clean_columns


def get_row_value(row, original_columns, clean_columns, col_name):
    clean_name = col_name.replace('\n', ' ')
    if clean_name in row.index:
        return clean_scalar(row[clean_name])
    for _orig_col, clean_col in zip(original_columns, clean_columns):
        if clean_col == clean_name:
            return clean_scalar(row[clean_col])
    return None


def build_product(row, original_columns, clean_columns):
    code_edi = clean_string(row['Code EDI'])
    product = {
        'code_EDI': code_edi,
        'Code Fabricant': 'SEI',
        'Marque': clean_string(get_row_value(row, original_columns, clean_columns, 'Marque'), 'SEIKO'),
        'Libelle': clean_string(get_row_value(row, original_columns, clean_columns, 'Libelle')),
        'Indice': clean_string(get_row_value(row, original_columns, clean_columns, 'Indice')),
        'Geometrie': clean_string(get_row_value(row, original_columns, clean_columns, 'Geometrie')),
        'Type': clean_string(get_row_value(row, original_columns, clean_columns, 'Type')),
        'Verres Spéciaux': clean_string(get_row_value(row, original_columns, clean_columns, 'Verres Spéciaux'), 'FALSE'),
        'Modele Verrier': clean_string(get_row_value(row, original_columns, clean_columns, 'Modele Verrier')),
        'Modele MDD': clean_string(get_row_value(row, original_columns, clean_columns, 'Modele MDD')),
        'Traitement Verrier': clean_string(get_row_value(row, original_columns, clean_columns, 'Traitement Verrier')),
        'Traitement MDD': clean_string(get_row_value(row, original_columns, clean_columns, 'Traitement MDD')),
        'STOCK / RX': clean_string(get_row_value(row, original_columns, clean_columns, 'STOCK / RX')),
        'TT OU NON TT': None,
        'OPTION\nVerrier': clean_scalar(get_row_value(row, original_columns, clean_columns, 'OPTION\nVerrier')),
        'OPTION\nMDD': clean_scalar(get_row_value(row, original_columns, clean_columns, 'OPTION\nMDD')),
        'OPTION\nMIROIR': clean_scalar(get_row_value(row, original_columns, clean_columns, 'OPTION\nMIROIR')),
        'OPTION\nDEGRADE': clean_scalar(get_row_value(row, original_columns, clean_columns, 'OPTION\nDEGRADE')),
        'OPTION\nUVBLS': clean_scalar(get_row_value(row, original_columns, clean_columns, 'OPTION\nUVBLS')),
        'OPTION\nPROTECTUV': None,
        'OPTION\nANTIBUEE': None,
        'OPTION\nSANSEQUIVALENCE': None,
        'LIBELLE CHAPEAU': clean_string(row.get('LIBELLE CHAPEAU', '')),
        'PVP': clean_string(row.get('PVP', '')),
        'Prix Achat Brut': clean_string(row.get('Prix Achat Brut', '')),
        'Prix Achat Net': clean_string(row.get('Prix Achat Net', '')),
        '% TOTAL REMISE': clean_string(row.get('% TOTAL REMISE', '')),
        'Net forcé': clean_string(row.get('Net forcé', 'FALSE'), 'FALSE'),
        'P2 MDD': None,
        'Verre supprimé': 'FALSE',
        'Date Suppression': '31/12/2154',
        'prix_reseau': {network: [] for network in NETWORKS},
    }
    return product


def build_products(report, pao_df, original_columns, clean_columns):
    products = {}
    for _, row in pao_df.iterrows():
        product = build_product(row, original_columns, clean_columns)
        products[product['code_EDI']] = product
    report['metrics']['generated_products'] = len(products)
    return products


def read_network_csv(report, network, csv_path):
    try:
        csv_df = pd.read_csv(csv_path, sep=';', header=None, names=CSV_COLUMNS, dtype=str, keep_default_na=False)
    except Exception as exc:
        fail(report, f'Lecture CSV impossible pour {network} ({csv_path.name}): {exc}')
    report['metrics']['csv_rows_by_network'][network] = int(len(csv_df))
    if csv_df.empty:
        if network in OPTIONAL_NETWORKS:
            add_warning(report, f'CSV réseau optionnel vide: {network}')
        else:
            add_error(report, f'CSV réseau obligatoire vide: {network}')
    csv_df['Code EDI'] = csv_df['Code EDI'].apply(lambda value: clean_string(value))
    return csv_df


def integrate_prices(report, products, csv_files):
    for network, csv_path in csv_files.items():
        csv_df = read_network_csv(report, network, csv_path)
        matched_codes = set()
        orphan_codes = set()

        for line_number, row in csv_df.iterrows():
            code_edi = clean_string(row['Code EDI'])
            if not code_edi:
                add_warning(report, f'{network}: ligne CSV {line_number + 1} ignorée, Code EDI vide')
                continue
            if code_edi not in products:
                orphan_codes.add(code_edi)
                continue

            try:
                price_entry = {
                    'sphère debut': finite_number(row['Sphere debut'], f'{network}/{code_edi}/sphère debut'),
                    'sphère fin': finite_number(row['Sphere fin'], f'{network}/{code_edi}/sphère fin'),
                    'Cylindre début': finite_number(row['Cylindre debut'], f'{network}/{code_edi}/Cylindre début'),
                    'Cylindre fin': finite_number(row['Cylindre fin'], f'{network}/{code_edi}/Cylindre fin'),
                    'PVP TTC': finite_number(row['PVP TTC'], f'{network}/{code_edi}/PVP TTC'),
                }
            except Exception as exc:
                add_error(report, f'{network}: plage invalide ligne CSV {line_number + 1}, code {code_edi}: {exc}')
                continue

            products[code_edi]['prix_reseau'][network].append(price_entry)
            matched_codes.add(code_edi)

        report['metrics']['csv_matched_codes_by_network'][network] = len(matched_codes)
        report['metrics']['csv_orphan_codes_by_network'][network] = len(orphan_codes)
        report['samples']['csv_orphan_codes'][network] = sorted(orphan_codes)[:REPORT_SAMPLE_LIMIT]


def validate_product_schema(report, products_list):
    if not isinstance(products_list, list):
        add_error(report, 'Le résultat final doit être une liste.')
        return

    expected = set(TARGET_KEYS)
    expected_networks = set(NETWORKS)
    for index, product in enumerate(products_list):
        code = product.get('code_EDI', f'index:{index}') if isinstance(product, dict) else f'index:{index}'
        if not isinstance(product, dict):
            add_error(report, f'Ligne {index}: la ligne doit être un objet JSON.')
            continue

        actual = set(product.keys())
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        if missing:
            add_error(report, f'{code}: clés manquantes: {missing}')
        if extra:
            add_error(report, f'{code}: clés supplémentaires: {extra}')

        prix_reseau = product.get('prix_reseau')
        if not isinstance(prix_reseau, dict):
            add_error(report, f'{code}: prix_reseau absent ou non objet.')
            continue

        actual_networks = set(prix_reseau.keys())
        missing_networks = sorted(expected_networks - actual_networks)
        extra_networks = sorted(actual_networks - expected_networks)
        if missing_networks:
            add_error(report, f'{code}: réseaux manquants: {missing_networks}')
        if extra_networks:
            add_error(report, f'{code}: réseaux supplémentaires: {extra_networks}')


def validate_required_product_values(report, products_list):
    seen_codes = set()
    duplicate_codes = set()
    for index, product in enumerate(products_list):
        if not isinstance(product, dict):
            continue
        code = clean_string(product.get('code_EDI'))
        if not code:
            add_error(report, f'Ligne {index}: code_EDI vide.')
        elif code in seen_codes:
            duplicate_codes.add(code)
        else:
            seen_codes.add(code)

        for field in REQUIRED_PRODUCT_NUMERIC_FIELDS:
            try:
                finite_catalog_number(product.get(field), f'{code or f"index:{index}"}/{field}')
            except Exception as exc:
                add_error(report, str(exc))

    if duplicate_codes:
        add_error(report, f'Codes EDI dupliqués dans le JSON final: {sorted(duplicate_codes)[:REPORT_SAMPLE_LIMIT]}')


def normalized_group_value(value):
    if value is None:
        return '(vide)'
    text = str(value).strip()
    return text if text else '(vide)'


def top_group_counts(products, field_name, limit=25):
    counts = {}
    for product in products:
        value = normalized_group_value(product.get(field_name))
        counts[value] = counts.get(value, 0) + 1
    return [
        {'value': value, 'count': count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def is_truthy_text(value):
    return str(value or '').strip().lower() in {'true', '1', 'oui', 'yes', 'y', 'vrai'}


def is_active_suppression_date(value):
    text = str(value or '').strip()
    return bool(text and text not in {'31/12/2154', '2154-12-31', '9999-12-31'})


def sample_products(products, fields=WITHOUT_PRICE_ANALYSIS_FIELDS, limit=REPORT_SAMPLE_LIMIT):
    return [
        {field: product.get(field) for field in fields}
        for product in products[:limit]
    ]


def build_hors_reseau_uniquement_report(report, hors_reseau_products):
    report['hors_reseau_uniquement'] = {
        'count': len(hors_reseau_products),
        'samples': sample_products(hors_reseau_products),
        'groupings': {
            field: top_group_counts(hors_reseau_products, field)
            for field in ['Modele Verrier', 'Modele MDD', 'Traitement Verrier', 'STOCK / RX', 'Libelle']
        },
    }


def normalize_edi_for_diagnostic(value):
    text = clean_string(value).upper().strip()
    if text.startswith('SEI'):
        text = text[3:]
    return ''.join(ch for ch in text if ch.isalnum())


def add_match(match_map, key, network, csv_code, line_number):
    if not key:
        return
    match_map.setdefault(key, []).append({
        'network': network,
        'csv_code': csv_code,
        'line': line_number,
    })


def read_csv_codes_for_diagnostic(report):
    exact_index = {}
    normalized_index = {}
    normalized_codes = set()
    csv_code_counts_by_network = {}

    for network, csv_path_value in report.get('files', {}).get('csv_files', {}).items():
        csv_path = Path(csv_path_value)
        try:
            csv_df = pd.read_csv(csv_path, sep=';', header=None, names=CSV_COLUMNS, dtype=str, keep_default_na=False)
        except Exception as exc:
            add_warning(report, f'Diagnostic EDI impossible pour {network}: lecture CSV échouée ({exc})')
            continue

        network_codes = set()
        for line_number, row in csv_df.iterrows():
            csv_code = clean_string(row['Code EDI'])
            if not csv_code:
                continue
            normalized_code = normalize_edi_for_diagnostic(csv_code)
            network_codes.add(csv_code)
            normalized_codes.add(normalized_code)
            add_match(exact_index, csv_code, network, csv_code, int(line_number) + 1)
            add_match(normalized_index, normalized_code, network, csv_code, int(line_number) + 1)
        csv_code_counts_by_network[network] = len(network_codes)

    return exact_index, normalized_index, sorted(normalized_codes), csv_code_counts_by_network


def summarize_matches(matches, limit=10):
    return [
        {
            'network': match['network'],
            'csv_code': match['csv_code'],
            'line': match['line'],
        }
        for match in matches[:limit]
    ]


def find_partial_matches(normalized_pao_code, normalized_csv_codes, normalized_index, limit=10):
    if not normalized_pao_code or len(normalized_pao_code) < 3:
        return []
    matches = []
    for csv_code in normalized_csv_codes:
        if csv_code == normalized_pao_code or len(csv_code) < 3:
            continue
        if normalized_pao_code in csv_code or csv_code in normalized_pao_code:
            for match in normalized_index.get(csv_code, []):
                matches.append(match)
                if len(matches) >= limit:
                    return matches
    return matches


def model_bucket(product):
    model = clean_string(product.get('Modele Verrier')).upper()
    for keyword in EDI_DIAGNOSTIC_MODEL_KEYWORDS:
        if keyword in model:
            return keyword
    return None


def build_without_price_edi_diagnostic(report, products_without_any_price):
    exact_index, normalized_index, normalized_csv_codes, csv_code_counts_by_network = read_csv_codes_for_diagnostic(report)
    exact_match_codes = []
    normalized_match_codes = []
    partial_match_codes = []
    no_match_codes = []
    exact_but_price_not_integrated = []
    examples_by_model = {
        keyword: {
            'total_without_price': 0,
            'no_match_samples': [],
            'exact_match_samples': [],
            'normalized_match_samples': [],
            'partial_match_samples': [],
        }
        for keyword in EDI_DIAGNOSTIC_MODEL_KEYWORDS
    }

    for product in products_without_any_price:
        code = clean_string(product.get('code_EDI'))
        normalized_code = normalize_edi_for_diagnostic(code)
        exact_matches = exact_index.get(code, [])
        normalized_matches = [
            match for match in normalized_index.get(normalized_code, [])
            if match['csv_code'] != code
        ]
        partial_matches = []
        if not exact_matches and not normalized_matches:
            partial_matches = find_partial_matches(normalized_code, normalized_csv_codes, normalized_index)

        result = {
            'code_EDI': code,
            'normalized_code': normalized_code,
            'Libelle': product.get('Libelle'),
            'Modele Verrier': product.get('Modele Verrier'),
            'Modele MDD': product.get('Modele MDD'),
            'Traitement Verrier': product.get('Traitement Verrier'),
            'STOCK / RX': product.get('STOCK / RX'),
            'exact_matches': summarize_matches(exact_matches),
            'normalized_matches': summarize_matches(normalized_matches),
            'partial_matches': summarize_matches(partial_matches),
        }

        bucket = model_bucket(product)
        if bucket:
            examples_by_model[bucket]['total_without_price'] += 1

        if exact_matches:
            exact_match_codes.append(result)
            exact_but_price_not_integrated.append(result)
            if bucket and len(examples_by_model[bucket]['exact_match_samples']) < 10:
                examples_by_model[bucket]['exact_match_samples'].append(result)
        elif normalized_matches:
            normalized_match_codes.append(result)
            if bucket and len(examples_by_model[bucket]['normalized_match_samples']) < 10:
                examples_by_model[bucket]['normalized_match_samples'].append(result)
        elif partial_matches:
            partial_match_codes.append(result)
            if bucket and len(examples_by_model[bucket]['partial_match_samples']) < 10:
                examples_by_model[bucket]['partial_match_samples'].append(result)
        else:
            no_match_codes.append(result)
            if bucket and len(examples_by_model[bucket]['no_match_samples']) < 10:
                examples_by_model[bucket]['no_match_samples'].append(result)

    if exact_but_price_not_integrated:
        likely_cause = 'mauvais format CSV ou valeurs prix/plages invalides'
        technical_recommendation = 'Inspecter les lignes CSV exactes: le code existe mais aucune plage valide n’a été intégrée.'
    elif normalized_match_codes or partial_match_codes:
        likely_cause = 'nettoyage EDI insuffisant'
        technical_recommendation = 'Ajouter une stratégie contrôlée de rapprochement EDI normalisé, avec rapport de confiance avant intégration.'
    elif no_match_codes and len(no_match_codes) == len(products_without_any_price):
        likely_cause = 'fichiers réseaux absents/incomplets ou verres hors réseaux'
        technical_recommendation = 'Demander confirmation métier: ces gammes actives doivent-elles être tarifées réseau ou exclues du catalogue réseau?'
    else:
        likely_cause = 'mixte'
        technical_recommendation = 'Traiter séparément les exact matches invalides, les rapprochements normalisés et les vrais absents réseau.'

    return {
        'analyzed_codes': len(products_without_any_price),
        'csv_code_counts_by_network': csv_code_counts_by_network,
        'exact_match_count': len(exact_match_codes),
        'normalized_match_count': len(normalized_match_codes),
        'partial_match_count': len(partial_match_codes),
        'no_match_count': len(no_match_codes),
        'exact_but_price_not_integrated_count': len(exact_but_price_not_integrated),
        'exact_but_price_not_integrated_samples': exact_but_price_not_integrated[:REPORT_SAMPLE_LIMIT],
        'normalized_match_samples': normalized_match_codes[:REPORT_SAMPLE_LIMIT],
        'partial_match_samples': partial_match_codes[:REPORT_SAMPLE_LIMIT],
        'no_match_samples': no_match_codes[:REPORT_SAMPLE_LIMIT],
        'examples_by_model': examples_by_model,
        'likely_cause': likely_cause,
        'technical_recommendation': technical_recommendation,
    }


def analyze_products_without_any_network_price(report, products_without_any_price):
    total = len(products_without_any_price)
    groupings = {
        field: top_group_counts(products_without_any_price, field)
        for field in WITHOUT_PRICE_GROUP_FIELDS
    }
    sample = sample_products(products_without_any_price)

    deleted_count = sum(1 for product in products_without_any_price if is_truthy_text(product.get('Verre supprimé')))
    active_suppression_date_count = sum(
        1 for product in products_without_any_price
        if is_active_suppression_date(product.get('Date Suppression'))
    )
    no_pvp_count = sum(1 for product in products_without_any_price if normalized_group_value(product.get('PVP')) == '(vide)')
    no_purchase_price_count = sum(
        1 for product in products_without_any_price
        if normalized_group_value(product.get('Prix Achat Net')) == '(vide)'
    )
    stock_rx_counts = {entry['value']: entry['count'] for entry in groupings.get('STOCK / RX', [])}
    geometry_counts = {entry['value']: entry['count'] for entry in groupings.get('Geometrie', [])}
    type_counts = {entry['value']: entry['count'] for entry in groupings.get('Type', [])}

    likely_deleted = deleted_count > 0 or active_suppression_date_count > 0
    likely_not_sellable = no_pvp_count / total >= 0.8 if total else False
    likely_out_of_network = total > 0 and deleted_count == 0 and active_suppression_date_count == 0
    likely_specific_ranges = any(
        token in ' '.join(list(geometry_counts.keys()) + list(type_counts.keys())).lower()
        for token in ['special', 'spécial', 'lenticular', 'degressif', 'bifocal', 'office', 'sport']
    )
    likely_edi_matching_anomaly = total > 0 and not likely_deleted and not likely_not_sellable

    if likely_deleted or active_suppression_date_count / total >= 0.5:
        recommendation = {
            'decision': 'exclure ces verres du catalogue',
            'reason': 'Une part significative semble supprimée ou datée comme supprimée.',
        }
    elif likely_not_sellable:
        recommendation = {
            'decision': 'transformer en warning sous conditions',
            'reason': 'Les verres sans prix semblent majoritairement non vendables car sans PVP exploitable.',
        }
    elif likely_edi_matching_anomaly:
        recommendation = {
            'decision': 'garder blocage',
            'reason': 'Les verres semblent actifs ou vendables mais absents de tous les tarifs réseau; vérifier le matching EDI ou les fichiers tarifs.',
        }
    else:
        recommendation = {
            'decision': 'garder blocage',
            'reason': 'Classification insuffisante pour autoriser ces verres sans prix.',
        }

    edi_diagnostic = build_without_price_edi_diagnostic(report, products_without_any_price)

    report['products_without_any_network_price_analysis'] = {
        'total': total,
        'sample_limit': REPORT_SAMPLE_LIMIT,
        'sample': sample,
        'groupings': groupings,
        'classification': {
            'seem_deleted': {
                'value': likely_deleted,
                'deleted_flag_count': deleted_count,
                'active_suppression_date_count': active_suppression_date_count,
            },
            'seem_not_sellable': {
                'value': likely_not_sellable,
                'empty_pvp_count': no_pvp_count,
                'empty_purchase_price_count': no_purchase_price_count,
            },
            'seem_out_of_network': {
                'value': likely_out_of_network,
                'reason': 'Aucun prix réseau sur tous les réseaux connus.',
            },
            'seem_specific_ranges': {
                'value': likely_specific_ranges,
                'top_geometries': groupings.get('Geometrie', [])[:10],
                'top_types': groupings.get('Type', [])[:10],
            },
            'seem_edi_matching_anomaly': {
                'value': likely_edi_matching_anomaly,
                'reason': 'Codes PAO présents mais absents de tous les tarifs réseau intégrés.',
            },
            'stock_rx_counts': stock_rx_counts,
        },
        'recommendation': recommendation,
        'edi_diagnostic': edi_diagnostic,
    }


def validate_price_ranges(report, products_list):
    expected_range_keys = set(NETWORK_RANGE_KEYS)
    products_without_any_price = []
    products_priced_by_network = {network: 0 for network in NETWORKS}

    for product in products_list:
        code = product['code_EDI']
        prix_reseau = product['prix_reseau']
        has_any_price = False

        for network in NETWORKS:
            ranges = prix_reseau.get(network)
            if not isinstance(ranges, list):
                add_error(report, f'{code}/{network}: prix_reseau réseau doit être un tableau.')
                continue
            if ranges:
                has_any_price = True
                products_priced_by_network[network] += 1

            for range_index, price_range in enumerate(ranges):
                context = f'{code}/{network}/plage:{range_index}'
                if not isinstance(price_range, dict):
                    add_error(report, f'{context}: la plage doit être un objet.')
                    continue
                actual_keys = set(price_range.keys())
                missing = sorted(expected_range_keys - actual_keys)
                extra = sorted(actual_keys - expected_range_keys)
                if missing:
                    add_error(report, f'{context}: clés de plage manquantes: {missing}')
                if extra:
                    add_error(report, f'{context}: clés de plage supplémentaires: {extra}')
                if missing or extra:
                    continue

                try:
                    sph_start = finite_number(price_range['sphère debut'], f'{context}/sphère debut')
                    sph_end = finite_number(price_range['sphère fin'], f'{context}/sphère fin')
                    cyl_start = finite_number(price_range['Cylindre début'], f'{context}/Cylindre début')
                    cyl_end = finite_number(price_range['Cylindre fin'], f'{context}/Cylindre fin')
                    pvp_ttc = finite_number(price_range['PVP TTC'], f'{context}/PVP TTC')
                except Exception as exc:
                    add_error(report, str(exc))
                    continue

                if sph_start > sph_end:
                    add_error(report, f'{context}: sphère debut > sphère fin')
                if cyl_start > cyl_end:
                    add_error(report, f'{context}: Cylindre début > Cylindre fin')
                if pvp_ttc <= 0:
                    add_error(report, f'{context}: PVP TTC <= 0')

        if not has_any_price:
            products_without_any_price.append(product)

    total = len(products_list)
    without_count = len(products_without_any_price)
    with_at_least_one_price = total - without_count
    ratio = without_count / total if total else 1
    empty_networks = [
        network for network, count in products_priced_by_network.items()
        if count == 0
    ]
    empty_required_networks = [network for network in empty_networks if network in REQUIRED_NETWORKS]
    empty_optional_networks = [network for network in empty_networks if network in OPTIONAL_NETWORKS]

    report['metrics']['generated_products'] = total
    report['metrics']['products_with_at_least_one_network_price'] = with_at_least_one_price
    report['metrics']['products_without_any_network_price'] = without_count
    report['metrics']['products_without_any_network_price_ratio'] = ratio
    report['metrics']['hors_reseau_uniquement_count'] = without_count
    report['metrics']['hors_reseau_uniquement_samples'] = sample_products(products_without_any_price)
    report['metrics']['priced_products_by_network'] = products_priced_by_network
    report['metrics']['empty_networks'] = empty_networks
    report['metrics']['products_priced_by_network'] = products_priced_by_network
    report['metrics']['empty_required_networks'] = empty_required_networks
    report['metrics']['empty_optional_networks'] = empty_optional_networks
    report['network_analysis']['csv_rows_by_network'] = report['metrics']['csv_rows_by_network']
    report['network_analysis']['matched_codes'] = report['metrics']['csv_matched_codes_by_network']
    report['network_analysis']['orphan_codes'] = report['metrics']['csv_orphan_codes_by_network']
    report['network_analysis']['empty_networks'] = empty_networks
    report['samples']['pao_codes_without_price'] = [
        product['code_EDI'] for product in products_without_any_price[:REPORT_SAMPLE_LIMIT]
    ]
    analyze_products_without_any_network_price(report, products_without_any_price)
    build_hors_reseau_uniquement_report(report, products_without_any_price)

    if products_without_any_price:
        add_warning(
            report,
            'Verres PAO hors réseau uniquement: '
            f'{without_count}/{total} ({ratio:.2%}). Conservés dans le candidat, indisponibles pour les réseaux sans prix.'
        )

    if empty_required_networks:
        add_error(report, f'Réseaux obligatoires entièrement vides: {empty_required_networks}')
    for network in empty_optional_networks:
        add_warning(report, f'Réseau optionnel absent ou entièrement vide: {network}')


def assert_no_nan_json(report, products_list):
    try:
        json_text = json.dumps(products_list, ensure_ascii=False, allow_nan=False)
    except ValueError as exc:
        add_error(report, f'Le JSON contient NaN/Infinity: {exc}')
        return
    if 'NaN' in json_text:
        add_error(report, 'Le JSON contient le token NaN.')


def validate_final_output(report, products_list):
    validate_product_schema(report, products_list)
    validate_required_product_values(report, products_list)
    validate_price_ranges(report, products_list)
    assert_no_nan_json(report, products_list)
    if report['errors']:
        fail(report)


def write_success_outputs(report, products_list):
    output_json = Path(report['files']['output_json'])
    with output_json.open('w', encoding='utf-8') as f:
        json.dump(products_list, f, ensure_ascii=False, indent=2, allow_nan=False)
    report['sha256'] = hashlib.sha256(output_json.read_bytes()).hexdigest()
    report['status'] = 'success'
    write_report(report)


def main():
    ensure_catalog_dirs()
    context = build_candidate_context()
    report = new_report(context)
    try:
        pao_file = find_pao_file(report)
        csv_files = find_csv_files(report)
        pao_df, original_columns, clean_columns = prepare_pao_dataframe(report, pao_file)
        products = build_products(report, pao_df, original_columns, clean_columns)
        integrate_prices(report, products, csv_files)
        products_list = list(products.values())
        validate_final_output(report, products_list)
        write_success_outputs(report, products_list)
        print(f'✅ Génération sécurisée réussie: {report["files"]["output_json"]}')
        print(f'✅ Rapport écrit: {REPORT_JSON}')
    except GenerationError:
        print(f'❌ Génération échouée. Rapport écrit: {REPORT_JSON}')
        raise SystemExit(1)
    except Exception as exc:
        fail(report, f'Erreur inattendue: {exc}')


if __name__ == '__main__':
    main()
