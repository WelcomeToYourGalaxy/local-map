#!/usr/bin/env python3
"""
wire_harvest.py  --  builds wire.json for the Global Wire on the activist map.

RUN ENVIRONMENT: GitHub Actions (scheduled), NOT the build sandbox.
OUTPUT: wire.json -- a TOP-LEVEL JSON ARRAY of {name,title,link,date,sig,snippet}.
The map checks Array.isArray(...), so the output MUST be an array, not an object.
Dependency: feedparser  (pip install feedparser)
"""
import json, time, datetime, html, re, os, calendar, unicodedata
import urllib.request, urllib.parse
import feedparser

# ---------------------------------------------------------------------------
# GEO-TAGGING: resolve each wire item to a country (ISO2) and, where possible,
# a subnational region, by scanning title+snippet against a worldwide gazetteer.
# The map's region filter reads item["iso"] and item["region"].
# Purely additive: an item that resolves to nothing is tagged iso=None.
# ---------------------------------------------------------------------------
# Country aliases -> ISO2. Kept deliberately broad but disambiguated (word-boundary
# matched at runtime). Demonyms included because headlines use them ("Brazilian dam").
_COUNTRY = {
 "US": ["united states","u.s.","u.s.a","usa","america","american"],
 "CA": ["canada","canadian"], "MX": ["mexico","mexican"],
 "BR": ["brazil","brazilian"], "AR": ["argentina","argentine","argentinian"],
 "CL": ["chile","chilean"], "PE": ["peru","peruvian"], "CO": ["colombia","colombian"],
 "EC": ["ecuador","ecuadorian"], "BO": ["bolivia","bolivian"], "VE": ["venezuela","venezuelan"],
 "PY": ["paraguay"], "UY": ["uruguay"], "GT": ["guatemala"], "HN": ["honduras"],
 "PA": ["panama"], "CR": ["costa rica"], "NI": ["nicaragua"], "DO": ["dominican republic"],
 "GB": ["united kingdom","britain","british","england","scotland","wales","northern ireland"," uk "],
 "IE": ["ireland","irish"], "FR": ["france","french"], "DE": ["germany","german"],
 "ES": ["spain","spanish"], "PT": ["portugal","portuguese"], "IT": ["italy","italian"],
 "NL": ["netherlands","dutch"], "BE": ["belgium","belgian"], "SE": ["sweden","swedish"],
 "NO": ["norway","norwegian"], "FI": ["finland","finnish"], "DK": ["denmark","danish"],
 "PL": ["poland","polish"], "CZ": ["czech"], "AT": ["austria","austrian"], "CH": ["switzerland","swiss"],
 "GR": ["greece","greek"], "RO": ["romania"], "HU": ["hungary"], "UA": ["ukraine","ukrainian"],
 "RU": ["russia","russian"], "TR": ["turkey","turkish","turkiye"], "RS": ["serbia"], "BG": ["bulgaria"],
 "HR": ["croatia"], "BA": ["bosnia"], "SK": ["slovakia"], "SI": ["slovenia"],
 "CN": ["china","chinese"], "IN": ["india","indian"], "PK": ["pakistan"], "BD": ["bangladesh"],
 "JP": ["japan","japanese"], "KR": ["south korea","korean","korea"], "ID": ["indonesia","indonesian"],
 "PH": ["philippines","philippine","filipino"], "VN": ["vietnam","vietnamese"], "TH": ["thailand","thai"],
 "MY": ["malaysia","malaysian"], "MM": ["myanmar","burma"], "KH": ["cambodia"], "LA": ["laos"],
 "NP": ["nepal"], "LK": ["sri lanka"], "KZ": ["kazakhstan"], "MN": ["mongolia"], "TW": ["taiwan","taiwanese"],
 "AU": ["australia","australian"], "NZ": ["new zealand"," nz "],
 "PG": ["papua new guinea"], "FJ": ["fiji"], "SB": ["solomon islands"],
 "ZA": ["south africa","south african"], "NG": ["nigeria","nigerian"], "KE": ["kenya","kenyan"],
 "GH": ["ghana"], "TZ": ["tanzania"], "UG": ["uganda"], "ET": ["ethiopia"], "CD": ["congo","drc"],
 "CG": ["republic of congo"], "CM": ["cameroon"], "CI": ["ivory coast","cote d'ivoire"],
 "SN": ["senegal"], "ML": ["mali"], "ZM": ["zambia"], "ZW": ["zimbabwe"], "MZ": ["mozambique"],
 "AO": ["angola"], "NA": ["namibia"], "BW": ["botswana"], "MG": ["madagascar"], "RW": ["rwanda"],
 "MA": ["morocco","moroccan"], "DZ": ["algeria"], "TN": ["tunisia"], "EG": ["egypt","egyptian"],
 "LY": ["libya"], "SD": ["sudan"], "SA": ["saudi arabia","saudi"], "AE": ["united arab emirates","uae"],
 "IL": ["israel","israeli"], "PS": ["palestine","palestinian","gaza","west bank"], "IQ": ["iraq","iraqi"],
 "IR": ["iran","iranian"], "SY": ["syria","syrian"], "JO": ["jordan"], "LB": ["lebanon"],
 "YE": ["yemen"], "OM": ["oman"], "QA": ["qatar"], "KW": ["kuwait"], "AZ": ["azerbaijan"],
 "GE": ["georgia"], "AM": ["armenia"], "UZ": ["uzbekistan"], "AF": ["afghanistan"],
}
# Subnational regions -> (ISO2, canonical region name). Federations + hotspots where
# fights are commonly datelined by state/province. Matched before country so a state
# name also resolves the country.
_REGION = {
 # US states (subset most datelined; extendable)
 "california":("US","California"),"texas":("US","Texas"),"florida":("US","Florida"),
 "new york":("US","New York"),"pennsylvania":("US","Pennsylvania"),"ohio":("US","Ohio"),
 "west virginia":("US","West Virginia"),"virginia":("US","Virginia"),"louisiana":("US","Louisiana"),
 "north dakota":("US","North Dakota"),"south dakota":("US","South Dakota"),"montana":("US","Montana"),
 "wyoming":("US","Wyoming"),"colorado":("US","Colorado"),"arizona":("US","Arizona"),
 "new mexico":("US","New Mexico"),"nevada":("US","Nevada"),"utah":("US","Utah"),
 "oregon":("US","Oregon"),"washington state":("US","Washington"),"alaska":("US","Alaska"),
 "minnesota":("US","Minnesota"),"wisconsin":("US","Wisconsin"),"michigan":("US","Michigan"),
 "illinois":("US","Illinois"),"georgia state":("US","Georgia"),"north carolina":("US","North Carolina"),
 "south carolina":("US","South Carolina"),"tennessee":("US","Tennessee"),"kentucky":("US","Kentucky"),
 "alabama":("US","Alabama"),"mississippi":("US","Mississippi"),"appalachia":("US","Appalachia"),
 # Canada
 "alberta":("CA","Alberta"),"british columbia":("CA","British Columbia"),"ontario":("CA","Ontario"),
 "quebec":("CA","Quebec"),"saskatchewan":("CA","Saskatchewan"),"manitoba":("CA","Manitoba"),
 "nova scotia":("CA","Nova Scotia"),"newfoundland":("CA","Newfoundland and Labrador"),
 # Australia
 "queensland":("AU","Queensland"),"new south wales":("AU","New South Wales"),"victoria":("AU","Victoria"),
 "western australia":("AU","Western Australia"),"south australia":("AU","South Australia"),
 "tasmania":("AU","Tasmania"),"northern territory":("AU","Northern Territory"),
 # Brazil
 "amazonas":("BR","Amazonas"),"para":("BR","Pará"),"mato grosso":("BR","Mato Grosso"),
 "minas gerais":("BR","Minas Gerais"),"bahia":("BR","Bahia"),"sao paulo":("BR","São Paulo"),
 "rondonia":("BR","Rondonia"),"maranhao":("BR","Maranhão"),
 # Argentina
 "mendoza":("AR","Mendoza"),"chubut":("AR","Chubut"),"catamarca":("AR","Catamarca"),
 "jujuy":("AR","Jujuy"),"neuquen":("AR","Neuquén"),"la rioja":("AR","La Rioja"),
 # India
 "odisha":("IN","Odisha"),"jharkhand":("IN","Jharkhand"),"chhattisgarh":("IN","Chhattisgarh"),
 "maharashtra":("IN","Maharashtra"),"goa":("IN","Goa"),"karnataka":("IN","Karnataka"),
 "tamil nadu":("IN","Tamil Nadu"),"gujarat":("IN","Gujarat"),"assam":("IN","Assam"),
 # Indonesia / Philippines / others
 "sumatra":("ID","Sumatra"),"kalimantan":("ID","Kalimantan"),"papua":("ID","Papua"),
 "sulawesi":("ID","Sulawesi"),"java":("ID","Java"),
 "mindanao":("PH","Mindanao"),"luzon":("PH","Luzon"),"palawan":("PH","Palawan"),
 # UK nations
 "scotland":("GB","Scotland"),"wales":("GB","Wales"),"northern ireland":("GB","Northern Ireland"),
 # Mexico / Chile / Peru hotspots
 "oaxaca":("MX","Oaxaca"),"chiapas":("MX","Chiapas"),"sonora":("MX","Sonora"),"yucatan":("MX","Yucatán"),
 "atacama":("CL","Atacama"),"antofagasta":("CL","Antofagasta"),"patagonia":("CL","Patagonia"),
 "cajamarca":("PE","Cajamarca"),"cusco":("PE","Cusco"),"puno":("PE","Puno"),
 # South Africa
 "mpumalanga":("ZA","Mpumalanga"),"limpopo":("ZA","Limpopo"),"kwazulu":("ZA","KwaZulu-Natal"),
 "eastern cape":("ZA","Eastern Cape"),
}
_GLOBAL_HINT = [" eu ","european union","european commission","united nations"," un ","u.n.","international",
 "worldwide","global","cross-border","transnational","treaty","cop28","cop29","cop30"]

def _geo_tag(text):
    """Return (iso, region) for a wire item. region may be '' if only country resolves.
    Multi-country or explicitly global items get iso='GL' (Global) so the filter can
    surface them under every region view as context."""
    s = " " + re.sub(r"[^a-z ]", " ", (text or "").lower()) + " "
    # region first (also fixes country)
    region = ""; iso = None
    for name, (cc, canon) in _REGION.items():
        if (" " + name + " ") in s:
            iso, region = cc, canon; break
    # countries: collect distinct hits
    hits = []
    for cc, aliases in _COUNTRY.items():
        for a in aliases:
            a2 = a if a.startswith(" ") or len(a) > 4 else " " + a + " "
            if a2 in s or (" " + a + " ") in s:
                hits.append(cc); break
    hits = list(dict.fromkeys(hits))
    if iso is None:
        if len(hits) == 1:
            iso = hits[0]
        elif len(hits) >= 2:
            iso = "GL"                      # multiple countries -> global/cross-border
    if any(h in s for h in _GLOBAL_HINT) and (iso is None or (region == "" and len(hits) >= 1 and iso != "GL")):
        # explicit global/bloc language present and no single clear local dateline -> global
        if region == "":
            iso = "GL"
    if iso and iso != "GL" and not region:
        _ms = _map_subregion(_A2TO3.get(iso, iso), text)   # map's own admin-1 taxonomy (+ capital-name forms)
        if _ms:
            region = _ms
    return iso, region


MOVEMENT = [
    # strict=True now: only items that name a concrete project/land-use fight get
    # through, and the weight is lower so scene round-ups stop dominating the wire.
    ("It's Going Down", "https://itsgoingdown.org/feed/", 3, True),
    ("Unicorn Riot",    "https://unicornriot.ninja/feed/", 3, True),
    ("Earth First! Journal", "https://earthfirstjournal.news/feed/", 3, True),
]
INVESTIGATIVE = [
    ("Grist",    "https://grist.org/feed/",          2, True),
    ("DeSmog",   "https://www.desmog.com/feed/",      2, True),
    ("Mongabay", "https://news.mongabay.com/feed/",   2, True),
    ("Inside Climate News", "https://insideclimatenews.org/feed/", 2, True),
    ("The Narwhal", "https://thenarwhal.ca/feed/",    2, True),
    ("Climate Home News", "https://www.climatechangenews.com/feed/", 2, True),
    ("Guardian Environment", "https://www.theguardian.com/environment/rss", 2, True),
    ("Mongabay Latam", "https://es.mongabay.com/feed/", 2, True),
    ("Mongabay India", "https://india.mongabay.com/feed/", 2, True),
    ("Mongabay Africa", "https://africa.mongabay.com/feed/", 2, True),
    ("The Third Pole", "https://www.thethirdpole.net/en/feed/", 2, True),
    ("Down To Earth (India)", "https://www.downtoearth.org.in/rss", 2, True),
]
FRONTS = [
    # A few high-profile US fights...
    "Mountain Valley Pipeline", "Line 5 pipeline", "Willow project Alaska drilling",
    "CP2 LNG terminal", "Resolution Copper Oak Flat",
    # ...balanced against major fights on every other continent, so the wire reads
    # as global coverage of the biggest, most irreversible projects.
    "EACOP East African Crude Oil Pipeline", "Uganda Tilenga oil drilling",
    "Adani Carmichael coal mine Australia", "Cerrejon coal mine Colombia",
    "Cobre Panama mine", "Rio Tinto Jadar lithium Serbia",
    "Grand Inga dam Congo", "ReconAfrica Okavango drilling",
    "Indonesia nickel mining Sulawesi deforestation", "Papua palm oil deforestation",
    "Amazon deforestation highway BR-319", "Trans Mountain pipeline Canada",
    "deep sea mining Pacific", "Balkans hydropower dam protest",
    "Hasdeo coal mine India", "Andes lithium mining protest",
    # --- Broadened country/region coverage: real, high-profile land & environmental
    # fights across every continent, so many more countries surface in the wire's
    # region filter. Each is a named fight that geo-resolves to its country.
    # Africa
    "Sengwer eviction Kenya forest", "Lamu coal plant Kenya", "Ogoni Shell cleanup Nigeria",
    "Niger Delta oil spill", "TotalEnergies Mozambique LNG Cabo Delgado", "Congo peatland oil auction",
    "Tanzania Uganda EACOP pipeline", "South Africa Wild Coast Shell seismic", "Xolobeni titanium mine",
    "Ghana bauxite Atewa forest", "Zambia copper mine pollution", "Zimbabwe Hwange coal",
    "Botswana Okavango oil drilling", "Madagascar mine Base Toliara", "Morocco Western Sahara phosphate",
    "DRC cobalt mining", "Ethiopia Gibe dam", "Senegal Bargny coal plant",
    # Asia
    "Philippines Kaliwa dam", "Philippines nickel mining Palawan", "Indonesia Rempang eco city eviction",
    "Indonesia Wadas quarry", "India Hasdeo Aranya coal", "India Great Nicobar project",
    "India Mumbai coastal road Aarey", "Bangladesh Rampal power plant Sundarbans", "Nepal Nijgadh airport forest",
    "Cambodia Koh Kong Cardamom", "Myanmar Myitsone dam", "Thailand Mekong dam protest",
    "Vietnam coal power Mekong delta", "Japan Henoko base landfill Okinawa", "South Korea Jeju naval base",
    "Malaysia Baram dam Sarawak", "Pakistan Reko Diq mine", "Sri Lanka Adani wind Mannar",
    "Mongolia Oyu Tolgoi mine water", "Kazakhstan uranium mining",
    # Latin America
    "Peru Conga mine", "Peru Tia Maria copper", "Bolivia lithium Salar de Uyuni",
    "Chile Dominga mine", "Chile Escondida water", "Argentina lithium Salinas Grandes",
    "Argentina Mendoza mining law protest", "Ecuador Yasuni oil drilling", "Ecuador Intag mining",
    "Colombia Hidroituango dam", "Brazil Belo Monte dam", "Brazil Ferrogrão railway Amazon",
    "Mexico Maya Train Tren Maya", "Mexico Dos Bocas refinery", "Panama Donoso copper mine",
    "Guatemala Escobal silver mine", "Honduras Guapinol river", "Venezuela Arco Minero Orinoco",
    # Europe
    "Serbia Rio Tinto Jadar lithium", "Portugal Barroso lithium mine", "Spain Aguas Tenidas mine",
    "Norway Fosen wind Sami", "Sweden Kallak iron mine", "Finland Terrafame mine",
    "Germany Lützerath coal mine", "France A69 motorway protest", "Italy TAP pipeline",
    "Greece Skouries gold mine", "Romania Rosia Montana", "Poland Turów coal mine",
    "UK Cumbria coal mine", "Ireland LNG Shannon",
    # Middle East / Caucasus / Pacific
    "Turkey Mount Ida gold mine Kaz", "Turkey Akbelen forest coal", "Armenia Amulsar gold mine",
    "Georgia Namakhvani dam", "Iran Karun dam", "Papua New Guinea Wafi Golpu mine",
    "Fiji seabed mining", "Australia Beetaloo fracking", "New Zealand seabed mining Taranaki",
    # generic global fronts (region-neutral phrasing)
    "Indigenous land defenders mine pipeline", "old growth logging protest",
    "LNG terminal opposition", "pipeline blockade protest",
]
# How far back the wire reaches. Google News queries are bounded with when:<N>d and
# every item -- from search or from a site's RSS -- is dropped if it is older, so the
# window stated in the panel is the window actually published.
WIRE_MAX_AGE_DAYS = int(os.environ.get("WIRE_MAX_AGE_DAYS", "60"))


def _too_old(item):
    """Drop by the window the item was actually gathered under. Regions with thin
    coverage are searched further back, so a blanket 30-day cut would delete exactly
    the items the widening was meant to find."""
    try:
        if isinstance(item, dict):
            days = int(item.get("widened") or WIRE_MAX_AGE_DAYS)
            date_ms = item.get("date")
        else:
            days, date_ms = WIRE_MAX_AGE_DAYS, item
        return (time.time() * 1000 - float(date_ms)) > days * 86400000.0
    except Exception:
        return False



# The map keys everything by alpha-3 ISO; the geo-tagger's country table is alpha-2,
# so items tagged by keyword could never match a region in the panel and every
# count read 0. Normalise on the way out so both pools speak the same code space.
_A2TO3 = {"AE": "ARE", "AF": "AFG", "AM": "ARM", "AO": "AGO", "AR": "ARG", "AT": "AUT", "AU": "AUS", "AZ": "AZE", "BD": "BGD", "BE": "BEL", "BO": "BOL", "BR": "BRA", "BW": "BWA", "CA": "CAN", "CD": "COD", "CH": "CHE", "CL": "CHL", "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI", "CZ": "CZE", "DE": "DEU", "DK": "DNK", "DO": "DOM", "DZ": "DZA", "EC": "ECU", "EG": "EGY", "ES": "ESP", "ET": "ETH", "FI": "FIN", "FJ": "FJI", "FR": "FRA", "GB": "GBR", "GE": "GEO", "GH": "GHA", "GR": "GRC", "GT": "GTM", "HN": "HND", "HU": "HUN", "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ", "IR": "IRN", "IT": "ITA", "JO": "JOR", "JP": "JPN", "KE": "KEN", "KR": "KOR", "KZ": "KAZ", "LB": "LBN", "LK": "LKA", "LY": "LBY", "MA": "MAR", "MG": "MDG", "ML": "MLI", "MM": "MMR", "MN": "MNG", "MX": "MEX", "MY": "MYS", "MZ": "MOZ", "NA": "NAM", "NG": "NGA", "NI": "NIC", "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL", "PA": "PAN", "PE": "PER", "PG": "PNG", "PH": "PHL", "PK": "PAK", "PL": "POL", "PS": "PSE", "PT": "PRT", "RO": "ROU", "RS": "SRB", "RU": "RUS", "RW": "RWA", "SA": "SAU", "SD": "SDN", "SE": "SWE", "SN": "SEN", "SY": "SYR", "TH": "THA", "TN": "TUN", "TR": "TUR", "TW": "TWN", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA", "UZ": "UZB", "VE": "VEN", "VN": "VNM", "YE": "YEM", "ZA": "ZAF", "ZM": "ZMB", "ZW": "ZWE"}


def _iso3(code):
    if not code:
        return code
    c = str(code).upper()
    if c == "GL" or len(c) == 3:
        return c
    return _A2TO3.get(c, c)

def google_news(q):
    from urllib.parse import quote
    return ("Front: " + q,
            "https://news.google.com/rss/search?q=%s+when:%dd&hl=en-US&gl=US&ceid=US:en"
            % (quote(q), WIRE_MAX_AGE_DAYS),
            2, True)

def _fold(s):
    """Lower-case and strip diacritics (Perú->peru, oleoduc<-oleoduc), leaving
    non-Latin scripts (Arabic, CJK, Cyrillic) intact so they can still match."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _norm_txt(s):
    """Fold, then keep letters of ANY script plus spaces. The old gate used
    [^a-z ], which deleted every accented and non-Latin character and made all
    non-English coverage unmatchable; this keeps it."""
    s = _fold(s)
    return " " + "".join(c if (c.isalpha() or c == " ") else " " for c in s) + " "


def _alias_hit(alias, t):
    """Match one normalized alias against normalized text t. ASCII words <=4
    chars must match whole-word (so 'chad' doesn't fire inside 'tchad'/'orchard');
    scripts without spaces (CJK) and longer aliases match as a substring."""
    if not alias:
        return False
    if alias.isascii() and len(alias) <= 4:
        return (" " + alias + " ") in t
    # space-separated whole-word for Latin phrases; substring for scripts w/o spaces
    if any(ch.isspace() for ch in alias) or alias.isascii():
        return alias in t
    return alias in t


# --- multilingual country-name aliases -----------------------------------------
# GDELT returns titles in the source language, so a French headline says "Tchad",
# a Spanish one "Perú", a Portuguese one "Brasil". Without these the name gate
# rejected genuine local-language coverage -- the very reporting this map exists
# to surface. Endonyms + Spanish/Portuguese/French exonyms + a verified set of
# native-script names. Merged through _fold so accents need not match exactly.

ALLOW = [
    "pipeline","lng","refinery","petrochemical","cracker plant","gas plant","power plant",
    "coal","oil","drilling","fracking","frack","well pad","compressor",
    "mine","mining","lithium","copper","quarry","tailings","strip mine","mountaintop",
    "clearcut","clear-cut","old growth","old-growth","logging","timber","deforestation",
    "wetland","waterway","aquifer","watershed","estuary","floodplain",
    "landfill","incinerator","cafo","factory farm","feedlot","hog farm",
    "data center","warehouse","distribution center","rezoning","zoning","subdivision","sprawl",
    "dam","reservoir","transmission line","substation","highway","interchange","port expansion",
    "blockade","tree sit","tree-sit","encampment","land defense","water protector","frontline",
    "eminent domain","easement","permit","comment period","draft eis","environmental review",
    "nepa","army corps","ferc","zoning board","planning commission","conservation easement",
    "hydropower","hydroelectric","palm oil","nickel","cobalt","bauxite","gold mine","copper mine",
    "crude oil pipeline","offshore drilling","seabed mining","deep-sea mining","megadam","reservoir dam",
    "land defender","land grab","evict","eviction","displacement","rainforest","peatland","mangrove","biodiversity",
    # development / land-use vocabulary the extractive-heavy list was missing, so
    # genuine project stories (dams, zones, farms, water schemes) are not dropped.
    "desalination","water rights","water scheme","irrigation","canal","aqueduct",
    "resettlement","expropriation","compensation","concession","land concession",
    "special economic zone","industrial park","industrial zone","free trade zone",
    "solar farm","solar park","wind farm","wind park","geothermal","biomass",
    "airport","rail line","railway","ring road","expressway","bridge project",
    "cement plant","steel plant","smelter","chemical plant","tannery","textile",
    "sand mining","dredging","coastal reclamation","land reclamation","real estate",
    "resort","tourism zone","new city","urban expansion","demolition","protected area",
    "national park","reserve","concession overlap","indigenous land","ancestral land",
    "environmental impact","eia","esia","public consultation","planning permission",
]
ALLOW = [_fold(k) for k in ALLOW]   # normalize so accented/multilingual terms match

# --- multilingual topic vocabulary --------------------------------------------
# The topic gate was English-only, so a real Spanish/Portuguese/French project
# story failed even when the country name matched. These are folded (accent-free)
# and pruned to avoid collisions (no bare 'tala' -> 'guaTALA', 'mina' -> 'laMINA',
# 'arena'=stadium, 'port'->airport). The name gate still backstops every one.
_ALLOW_ML = [
 # Spanish
 "mineria","mina de","oleoducto","gasoducto","represa","embalse","hidroelectrica",
 "termoelectrica","deforestacion","petroleo","perforacion","contaminacion","concesion",
 "expropiacion","desalojo","refineria","vertedero","relave","litio","aeropuerto",
 "autopista","dragado","consulta previa","licencia ambiental","area protegida",
 "central nuclear","planta de carbon","desalinizacion","tierras indigenas",
 # Portuguese
 "mineracao","oleoduto","gasoduto","barragem","desmatamento","hidreletrica",
 "termeletrica","perfuracao","poluicao","concessao","desapropriacao","refinaria",
 "aterro","litio","aeroporto","rodovia","dragagem","licenciamento ambiental",
 "terra indigena","usina hidreletrica","usina termeletrica","desalinizacao",
 # French
 "oleoduc","gazoduc","barrage","deforestation","petrole","forage","hydroelectrique",
 "raffinerie","decharge","aeroport","autoroute","dragage","expropriation","expulsion",
 "exploitation miniere","mine de","aire protegee","terres autochtones",
 "cuivre","centrale a charbon","centrale nucleaire","dessalement",
]
ALLOW = ALLOW + [_fold(k) for k in _ALLOW_ML]

def matches(text):
    t = " " + _fold(text) + " "
    for k in ALLOW:
        # short ASCII keywords match whole-word only (so 'nepa' doesn't fire inside
        # 'nepal', 'esia' inside 'indonesia', 'mine' inside 'examined'); longer
        # terms, phrases, and non-Latin scripts match as substring.
        if k.isascii() and len(k) <= 5 and " " not in k:
            if (" " + k + " ") in t:
                return True
        elif k in t:
            return True
    return False

# --- off-topic stop-list (multilingual) ---------------------------------------
# ALLOW/matches() decides what to KEEP; this decides what to DROP outright, even
# when a topic word is also present. Sport, crime blotter, celebrity, markets and
# pure horse-race politics are the recurring noise -- and foreign GDELT items skip
# the English topic gate, so without this they arrive unfiltered. Folded
# (accent-free) so ES/PT/FR forms match; short ASCII terms match whole-word only.
_BLOCK = [
 # sport
 "goalkeeper","midfielder","striker","winger","world cup","transfer window","signed for",
 "signs for","football club","premier league","la liga","serie a","bundesliga","champions league",
 "cup final","league title","grand prix","formula 1","touchdown","home run","cricket","wicket",
 "tournament","stadium","world champion","olympic","medal",
 "futbol","futebol","gol de","liga mx","seleccion","selecao","jogador","jugador","entraineur",
 # crime blotter / personal-court items (not project litigation)
 "sentenced to death","death penalty","capital punishment","death row","homicide","murder trial",
 "murder case","serial killer","execution","stabbing","gunman","kidnapping","rape","armed robbery",
 "pena de muerte","pena de morte","peine de mort","homicidio","homicidio","asesinato","assassinato",
 "condenado a muerte","condamne a mort",
 # celebrity / culture / markets
 "celebrity","box office","red carpet","concert tour","horoscope","royal wedding",
 "stock market","earnings call","quarterly earnings","bitcoin","shares rise","shares fall","obituary",
]
_BLOCK = [_fold(k) for k in _BLOCK]

def _blocked(text):
    """True if the item is off-topic noise that must be dropped regardless of any
    topic-word match. Multilingual (folded); short ASCII terms are whole-word so
    they do not fire inside longer words."""
    t = " " + _fold(text) + " "
    for k in _BLOCK:
        if k.isascii() and len(k) <= 5 and " " not in k:
            if (" " + k + " ") in t:
                return True
        elif k in t:
            return True
    return False


def clean(s):
    return html.unescape(re.sub("<[^>]+>", "", s or "")).strip()

def collect():
    feeds = list(MOVEMENT) + list(INVESTIGATIVE) + [google_news(q) for q in FRONTS]
    seen, items = set(), []
    for name, url, weight, strict in feeds:
        try:
            fp = feedparser.parse(url)
        except Exception as e:
            print("  feed %s failed: %s" % (name, e)); continue
        per_feed = 0
        for e in fp.entries[:60]:
            if per_feed >= 6:
                break
            title = clean(e.get("title"))
            summary = clean(e.get("summary", ""))
            link = e.get("link", "")
            if not title or not link:
                continue
            blob = title + " " + summary
            if _blocked(blob):
                continue
            if strict and not matches(blob):
                continue
            key = re.sub(r"[^a-z0-9]", "", title.lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            per_feed += 1
            ts = None
            for f in ("published_parsed", "updated_parsed"):
                if e.get(f):
                    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", e.get(f)); break
            hits = sum(1 for k in ALLOW if k in blob.lower())
            recent = ts and ts[:10] >= (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
            score = weight * 10 + hits + (5 if recent else 0)
            date_ms = 0
            if ts:
                try: date_ms = int(calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")) * 1000)
                except Exception: date_ms = 0
            if not date_ms:
                date_ms = int(time.time() * 1000)
            _iso, _region = _geo_tag(title + " " + summary)
            _iso = _iso3(_iso)
            items.append({"name": name, "title": title[:200], "link": link,
                          "date": date_ms, "sig": weight, "snippet": summary[:280],
                          "iso": _iso, "region": _region, "score": score})
    items.sort(key=lambda x: -x["score"])
    return items


# --- per-region sweep -------------------------------------------------------
# The wire used to run topic queries and then guess a region from keywords, so a
# region only ever appeared if some generic story happened to mention it. This
# list drives one query PER region instead, and tags each item with that ISO
# directly -- every region gets its own feed rather than a share of a global pool.
_WIRE_REGIONS = {
"USA": "United States",
"CAN": "Canada",
"COL": "Colombia",
"ARG": "Argentina",
"CHL": "Chile",
"BRA": "Brazil",
"MEX": "Mexico",
"GTM": "Guatemala",
"ECU": "Ecuador",
"PER": "Peru",
"CRI": "Costa Rica",
"HND": "Honduras",
"VEN": "Venezuela",
"PAN": "Panama",
"DOM": "Dominican Republic",
"GBR": "United Kingdom",
"DEU": "Germany",
"FRA": "France",
"ITA": "Italy",
"ESP": "Spain",
"GRC": "Greece",
"CZE": "Czech Republic",
"IRL": "Ireland",
"AUT": "Austria",
"NLD": "Netherlands",
"DNK": "Denmark",
"NOR": "Norway",
"SWE": "Sweden",
"POL": "Poland",
"ROU": "Romania",
"SRB": "Serbia",
"UKR": "Ukraine",
"HUN": "Hungary",
"SVK": "Slovakia",
"LUX": "Luxembourg",
"ALB": "Albania",
"GEO": "Georgia",
"MDA": "Moldova",
"BIH": "Bosnia and Herzegovina",
"XKX": "Kosovo",
"MKD": "North Macedonia",
"MNE": "Montenegro",
"KEN": "Kenya",
"ZAF": "South Africa",
"GHA": "Ghana",
"NGA": "Nigeria",
"TUN": "Tunisia",
"MAR": "Morocco",
"UGA": "Uganda",
"TZA": "Tanzania",
"ISR": "Israel",
"JOR": "Jordan",
"LBN": "Lebanon",
"IND": "India",
"MYS": "Malaysia",
"JPN": "Japan",
"KOR": "South Korea",
"TWN": "Taiwan",
"PHL": "Philippines",
"ARM": "Armenia",
"AUS": "Australia",
"NZL": "New Zealand",
"HRV": "Croatia",
"CHE": "Switzerland",
"BEL": "Belgium",
"BGR": "Bulgaria",
"EST": "Estonia",
"FIN": "Finland",
"PRT": "Portugal",
"LVA": "Latvia",
"LTU": "Lithuania",
"ISL": "Iceland",
"SVN": "Slovenia",
"CYP": "Cyprus",
"PAK": "Pakistan",
"LKA": "Sri Lanka",
"BGD": "Bangladesh",
"THA": "Thailand",
"IDN": "Indonesia",
"SGP": "Singapore",
"URY": "Uruguay",
"BOL": "Bolivia",
"SLV": "El Salvador",
"PRY": "Paraguay",
"ZMB": "Zambia",
"EGY": "Egypt",
"SEN": "Senegal",
"RWA": "Rwanda",
"ETH": "Ethiopia",
"FJI": "Fiji",
"PNG": "Papua New Guinea",
"TUR": "Turkey",
"MLT": "Malta",
"RUS": "Russia",
"BLR": "Belarus",
"AZE": "Azerbaijan",
"MNG": "Mongolia",
"MDV": "Maldives",
"PSE": "Palestine",
"IRQ": "Iraq",
"KAZ": "Kazakhstan",
"KWT": "Kuwait",
"KGZ": "Kyrgyzstan",
"NPL": "Nepal",
"KHM": "Cambodia",
"TLS": "Timor-Leste",
"ZWE": "Zimbabwe",
"LBR": "Liberia",
"MWI": "Malawi",
"MOZ": "Mozambique",
"SLE": "Sierra Leone",
"BWA": "Botswana",
"MUS": "Mauritius",
"BFA": "Burkina Faso",
"MDG": "Madagascar",
"COD": "DRC (Congo)",
"SSD": "South Sudan",
"NAM": "Namibia",
"HTI": "Haiti",
"TTO": "Trinidad & Tobago",
"SUR": "Suriname",
"JAM": "Jamaica",
"GUY": "Guyana",
"VUT": "Vanuatu",
"SLB": "Solomon Islands",
"CUB": "Cuba",
"NIC": "Nicaragua",
"CHN": "China",
"IRN": "Iran",
"CIV": "Côte d’Ivoire",
"CMR": "Cameroon",
"BEN": "Benin",
"VNM": "Vietnam",
"BTN": "Bhutan",
"CPV": "Cabo Verde",
"GMB": "Gambia",
"TGO": "Togo",
"AND": "Andorra",
"ATG": "Antigua and Barbuda",
"BHS": "Bahamas",
"BRB": "Barbados",
"BLZ": "Belize",
"DMA": "Dominica",
"GRD": "Grenada",
"KNA": "St Kitts and Nevis",
"LCA": "St Lucia",
"VCT": "St Vincent and the Grenadines",
"DZA": "Algeria",
"AGO": "Angola",
"BDI": "Burundi",
"TCD": "Chad",
"COM": "Comoros",
"COG": "Republic of the Congo",
"DJI": "Djibouti",
"GAB": "Gabon",
"GIN": "Guinea",
"GNB": "Guinea-Bissau",
"LSO": "Lesotho",
"LBY": "Libya",
"MLI": "Mali",
"MRT": "Mauritania",
"NER": "Niger",
"STP": "São Tomé and Príncipe",
"SYC": "Seychelles",
"SOM": "Somalia",
"SDN": "Sudan",
"SWZ": "Eswatini",
"KIR": "Kiribati",
"MHL": "Marshall Islands",
"FSM": "Micronesia",
"PLW": "Palau",
"WSM": "Samoa",
"TON": "Tonga",
"TUV": "Tuvalu",
"BHR": "Bahrain",
"BRN": "Brunei",
"OMN": "Oman",
"QAT": "Qatar",
"SAU": "Saudi Arabia",
"ARE": "United Arab Emirates",
"YEM": "Yemen",
"LAO": "Laos",
"MMR": "Myanmar",
"AFG": "Afghanistan",
"UZB": "Uzbekistan",
"TJK": "Tajikistan",
"MCO": "Monaco",
"LIE": "Liechtenstein",
"SMR": "San Marino",
"HKG": "Hong Kong",
"MAC": "Macau",
"GRL": "Greenland",
"FRO": "Faroe Islands",
"TKM": "Turkmenistan",
"ERI": "Eritrea",
"PRK": "North Korea",
"GNQ": "Equatorial Guinea",
"SYR": "Syria",
"NRU": "Nauru",
"CAF": "Central African Republic",
"ALA": "Åland",
"BMU": "Bermuda",
"NIU": "Niue",
"PRI": "Puerto Rico",
"COK": "Cook Islands",
"VAT": "Vatican City",
"JEY": "Jersey",
"CYM": "Cayman Islands",
"GIB": "Gibraltar",
"AIA": "Anguilla",
"MSR": "Montserrat",
"XKS": "Kosovo"
}

_REGION_TERMS = ("protest OR opposition OR lawsuit OR injunction OR permit OR "
                 "mine OR pipeline OR dam OR drilling OR deforestation OR eviction "
                 "OR \"environmental impact\" OR indigenous OR land rights")



# Google News locale per region, so a sweep for, say, Senegal or Vietnam searches in
# the language the coverage is actually published in. Anything not listed falls back
# to English, which is fine for anglophone and small-media states.
_REGION_LOCALE = {
 "BRA":("pt-BR","BR"),"PRT":("pt-PT","PT"),"AGO":("pt-PT","AO"),"MOZ":("pt-PT","MZ"),
 "ESP":("es","ES"),"MEX":("es-419","MX"),"ARG":("es-419","AR"),"COL":("es-419","CO"),
 "CHL":("es-419","CL"),"PER":("es-419","PE"),"VEN":("es-419","VE"),"ECU":("es-419","EC"),
 "BOL":("es-419","BO"),"GTM":("es-419","GT"),"HND":("es-419","HN"),"NIC":("es-419","NI"),
 "CRI":("es-419","CR"),"PAN":("es-419","PA"),"DOM":("es-419","DO"),"URY":("es-419","UY"),
 "PRY":("es-419","PY"),"SLV":("es-419","SV"),"CUB":("es-419","CU"),
 "FRA":("fr","FR"),"BEL":("fr","BE"),"SEN":("fr","SN"),"CIV":("fr","CI"),"MLI":("fr","ML"),
 "BFA":("fr","BF"),"NER":("fr","NE"),"TCD":("fr","TD"),"CMR":("fr","CM"),"GAB":("fr","GA"),
 "COG":("fr","CG"),"COD":("fr","CD"),"MDG":("fr","MG"),"GIN":("fr","GN"),"BEN":("fr","BJ"),
 "TGO":("fr","TG"),"HTI":("fr","HT"),
 "DEU":("de","DE"),"AUT":("de","AT"),"CHE":("de","CH"),"ITA":("it","IT"),"NLD":("nl","NL"),
 "POL":("pl","PL"),"SWE":("sv","SE"),"NOR":("no","NO"),"DNK":("da","DK"),"FIN":("fi","FI"),
 "GRC":("el","GR"),"ROU":("ro","RO"),"CZE":("cs","CZ"),"HUN":("hu","HU"),"BGR":("bg","BG"),
 "HRV":("hr","HR"),"SRB":("sr","RS"),"SVK":("sk","SK"),"SVN":("sl","SI"),"UKR":("uk","UA"),
 "RUS":("ru","RU"),"BLR":("ru","BY"),"KAZ":("ru","KZ"),"UZB":("ru","UZ"),
 "TUR":("tr","TR"),"IRN":("fa","IR"),"ISR":("he","IL"),
 "SAU":("ar","SA"),"EGY":("ar","EG"),"ARE":("ar","AE"),"IRQ":("ar","IQ"),"JOR":("ar","JO"),
 "DZA":("ar","DZ"),"MAR":("ar","MA"),"TUN":("ar","TN"),"LBY":("ar","LY"),"LBN":("ar","LB"),
 "KWT":("ar","KW"),"QAT":("ar","QA"),"OMN":("ar","OM"),"YEM":("ar","YE"),"SDN":("ar","SD"),
 "CHN":("zh-CN","CN"),"TWN":("zh-TW","TW"),"JPN":("ja","JP"),"KOR":("ko","KR"),
 "IDN":("id","ID"),"THA":("th","TH"),"VNM":("vi","VN"),"MMR":("my","MM"),"KHM":("km","KH"),
 "IND":("hi","IN"),"PAK":("ur","PK"),"BGD":("bn","BD"),"NPL":("ne","NP"),"LKA":("si","LK"),
 "ETH":("am","ET"),"TZA":("sw","TZ"),"KEN":("sw","KE"),
}

# Progressive widening. A single 30-day English query returns nothing at all for small
# or non-anglophone states, which is why almost every region read 0. Each region walks
# these tiers until it finds something: tighter and more recent first, then broader
# terms, a longer window, the local language, and finally the bare region name.

# --- per-region relevance gate ------------------------------------------------
# GDELT matches a bare country name as a *substring anywhere*, so a query for
# "Chad" returned US celebrity and pipeline stories that merely contained the
# word. Before keeping an item under a region we now require the region's own
# name (or a known alias) to actually appear in the title or snippet, and we run
# the gazetteer to attach a subnational region where one is named.
_ISO3_ALIASES = {}
for _cc2, _al in _COUNTRY.items():
    _cc3 = _A2TO3.get(_cc2)
    if _cc3:
        _ISO3_ALIASES.setdefault(_cc3, set()).update(a.strip().lower() for a in _al)
# make sure every swept region has at least its display name as an alias
for _iso, _nm in _WIRE_REGIONS.items():
    _ISO3_ALIASES.setdefault(_iso, set()).add((_nm or "").strip().lower())
    # a couple of common adjectival / short forms the gazetteer may lack
    _low = (_nm or "").lower()
    if _low:
        _ISO3_ALIASES[_iso].add(_low)



# A curated set of unambiguous extra aliases (capital cities, demonyms) so a real
# story that names the capital or nationality but not the country still resolves.
# Kept conservative on purpose -- an alias that collides with an ordinary English
# word would re-open the false-positive door that this whole gate exists to close.
_EXTRA_ALIASES = {
 "TCD": ["chadian", "ndjamena", "n'djamena", "doba"],
 "GTM": ["guatemalan"], "HND": ["honduran", "tegucigalpa"],
 "PAN": ["panamanian"], "DOM": ["dominican"], "CRI": ["costa rican", "san jose"],
 "ROU": ["romanian", "bucharest"], "SRB": ["serbian", "belgrade"],
 "HUN": ["hungarian", "budapest"], "SVK": ["slovak", "bratislava"],
 "ALB": ["albanian", "tirana"], "MDA": ["moldovan", "chisinau"],
 "MKD": ["macedonian", "skopje"], "MNE": ["montenegrin", "podgorica"],
 "GHA": ["ghanaian", "accra"], "TUN": ["tunisian"], "UGA": ["ugandan", "kampala"],
 "TZA": ["tanzanian", "dodoma", "dar es salaam"], "JOR": ["jordanian", "amman"],
 "LBN": ["lebanese", "beirut"], "ARM": ["armenian", "yerevan"],
 "HRV": ["croatian", "zagreb"], "SEN": ["senegalese", "dakar"],
 "CMR": ["cameroonian", "yaounde"], "CIV": ["ivorian", "abidjan", "ivory coast"],
 "ZMB": ["zambian", "lusaka"], "ZWE": ["zimbabwean", "harare"],
 "MOZ": ["mozambican", "maputo"], "AGO": ["angolan", "luanda"],
 "BWA": ["botswana", "gaborone"], "NAM": ["namibian", "windhoek"],
 "MWI": ["malawian", "lilongwe"], "RWA": ["rwandan", "kigali"],
 "KHM": ["cambodian", "phnom penh"], "LAO": ["laotian", "vientiane"],
 "MMR": ["myanmar", "burmese", "naypyidaw", "yangon"],
 "NPL": ["nepali", "nepalese", "kathmandu"], "LKA": ["sri lankan", "colombo"],
 "MNG": ["mongolian", "ulaanbaatar"], "KAZ": ["kazakh", "astana", "almaty"],
 "PRY": ["paraguayan", "asuncion"], "URY": ["uruguayan", "montevideo"],
 "BOL": ["bolivian", "la paz"], "PAN": ["panamanian"],
 "MAR": ["moroccan", "rabat"], "DZA": ["algerian", "algiers"],
 "ETH": ["ethiopian", "addis ababa"], "KEN": ["kenyan", "nairobi"],
 "NGA": ["nigerian", "abuja", "lagos"], "EGY": ["egyptian", "cairo"],
}
for _iso, _al in _EXTRA_ALIASES.items():
    _ISO3_ALIASES.setdefault(_iso, set()).update(a.strip().lower() for a in _al)


_LANG_ALIASES = {
 "BRA": ["brasil"],
 "MEX": ["mexique"],
 "PER": ["perou"],
 "CHL": ["chili"],
 "COL": ["colombie"],
 "ARG": ["argentine"],
 "ECU": ["equateur"],
 "BOL": ["bolivie"],
 "VEN": ["venezuela"],
 "URY": ["uruguay"],
 "PRY": ["paraguay"],
 "GTM": ["guatemala"],
 "HND": ["honduras"],
 "CRI": ["costa rica"],
 "PAN": ["panama", "panama"],
 "DOM": ["republique dominicaine", "republica dominicana"],
 "TCD": ["tchad", "تشاد"],
 "CIV": ["cote d ivoire", "costa de marfil"],
 "SEN": ["senegal", "senegal"],
 "CMR": ["cameroun", "camerun"],
 "COD": ["republique democratique du congo", "rd congo", "rdc", "congo kinshasa"],
 "COG": ["congo brazzaville", "republique du congo"],
 "MLI": ["mali"],
 "NER": ["niger"],
 "BFA": ["burkina faso"],
 "GIN": ["guinee", "guinea"],
 "MDG": ["madagascar"],
 "MAR": ["maroc", "marruecos", "المغرب"],
 "DZA": ["algerie", "argelia", "الجزائر"],
 "TUN": ["tunisie", "tunez", "تونس"],
 "EGY": ["egypte", "egipto", "مصر"],
 "ETH": ["ethiopie", "etiopia"],
 "AGO": ["angola"],
 "MOZ": ["mocambique", "mozambique"],
 "GNB": ["guinee bissau", "guinea bissau"],
 "KHM": ["cambodge", "camboya"],
 "LAO": ["laos"],
 "VNM": ["vietnam", "viet nam", "越南"],
 "MMR": ["birmanie", "birmania"],
 "IDN": ["indonesie", "indonesia"],
 "PHL": ["philippines", "filipinas"],
 "THA": ["thailande", "tailandia", "泰国"],
 "CHN": ["chine", "china", "中国"],
 "JPN": ["japon", "日本"],
 "KOR": ["coree du sud", "corea del sur", "한국"],
 "IND": ["inde", "india", "भारत"],
 "PAK": ["pakistan"],
 "BGD": ["bangladesh"],
 "LKA": ["sri lanka"],
 "NPL": ["nepal"],
 "DEU": ["deutschland", "allemagne", "alemania"],
 "FRA": ["france", "francia"],
 "ESP": ["espana", "espagne"],
 "ITA": ["italie", "italia"],
 "PRT": ["portugal"],
 "RUS": ["russie", "rusia", "россия"],
 "UKR": ["ukraine", "ucrania", "украина"],
 "TUR": ["turquie", "turquia", "turkiye"],
 "GRC": ["grece", "grecia"],
 "POL": ["pologne", "polonia", "polska"],
 "NGA": ["nigeria", "nigeria"],
 "KEN": ["kenya", "kenia"],
 "TZA": ["tanzanie", "tanzania"],
 "UGA": ["ouganda", "uganda"],
 "ZMB": ["zambie", "zambia"],
 "ZWE": ["zimbabwe"],
 "GHA": ["ghana"],
 "ZAF": ["afrique du sud", "sudafrica"],
 "BWA": ["botswana"],
 "NAM": ["namibie", "namibia"],
 "SAU": ["arabie saoudite", "arabia saudita", "السعودية"],
 "IRQ": ["irak", "iraq", "العراق"],
 "JOR": ["jordanie", "jordania", "الأردن"],
 "LBN": ["liban", "libano", "لبنان"],
}
for _iso, _al in _LANG_ALIASES.items():
    _ISO3_ALIASES.setdefault(_iso, set()).update(_fold(a) for a in _al)

def _region_named(iso, text):
    """True if the region iso is actually named in the item text -- by its own
    name/alias in any language we carry, OR by a subnational unit that the
    gazetteer resolves to this country (a story naming only 'California' or
    'Cajamarca' still belongs to its country)."""
    t = _norm_txt(text)
    for a in _ISO3_ALIASES.get(iso, ()):
        if _alias_hit(_fold(a), t):
            return True
    if _subregion_for(iso, text):     # a gazetteer subnational hit implies the country
        return True
    return False


# English aliases for endonym-keyed map subregions (e.g. Bayern->Bavaria), so
# English-language news matches the canonical trackerData key.
_SUB_ALIAS = {"Bayern": "Bavaria", "Niedersachsen": "Lower Saxony", "Nordrhein-Westfalen": "North Rhine-Westphalia", "Rheinland-Pfalz": "Rhineland-Palatinate", "Sachsen": "Saxony", "Sachsen-Anhalt": "Saxony-Anhalt", "Thüringen": "Thuringia", "Hessen": "Hesse", "Mecklenburg-Vorpommern": "Mecklenburg-W. Pomerania", "Lombardia": "Lombardy", "Piemonte": "Piedmont", "Toscana": "Tuscany", "Sicilia": "Sicily", "Sardegna": "Sardinia", "Puglia": "Apulia", "Trentino-Alto Adige/Sudtirol": "Trentino-South Tyrol", "Cataluña": "Catalonia", "Andalucía": "Andalusia", "País Vasco": "Basque Country", "Aragón": "Aragon", "Castilla y León": "Castile and León", "Castilla-La Mancha": "Castile-La Mancha", "Islas Baleares": "Balearic Islands", "Canary Is.": "Canary Islands", "Foral de Navarra": "Navarre", "Valenciana": "Valencia", "Bretagne": "Brittany", "Normandie": "Normandy", "Corse": "Corsica", "Kärnten": "Carinthia", "Steiermark": "Styria", "Tirol": "Tyrol", "Niederösterreich": "Lower Austria", "Oberösterreich": "Upper Austria", "Wien": "Vienna", "Genève": "Geneva", "Zürich": "Zurich", "Graubünden": "Grisons", "Noord-Holland": "North Holland", "Zuid-Holland": "South Holland", "Zeeland": "Zealand", "Noord-Brabant": "North Brabant"}

def _slugify(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()

# Admin-level suffixes/prefixes stripped so a bucket named after its capital matches the
# city the news actually names ("Lagos State"->"Lagos", "Kharkiv Oblast"->"Kharkiv").
_SUB_SUFFIX = re.compile(r'\b(state|province|prov|region|regional|oblast|krai|raion|okrug|'
    r'department|departamento|prefecture|governorate|district|county|voivodeship|canton|'
    r'emirate|territory|autonomous|municipality|metropolitan|greater|city|province of|'
    r'state of|region of|and islands)\b')
def _strip_suffix(slug):
    return re.sub(r'\s+', ' ', _SUB_SUFFIX.sub(' ', slug)).strip()

# The map's own subregion taxonomy is the source of truth: assign region strings that are
# byte-for-byte the trackerData sub keys, so the front-end join always lands (no
# writer/reader mismatch). Loaded once from trackerdata.json in the repo.
_MAP_SUBS = None
def _load_map_subregions():
    global _MAP_SUBS
    if _MAP_SUBS is not None:
        return _MAP_SUBS
    _MAP_SUBS = {}
    for path in ("trackerdata.json", os.path.join(os.path.dirname(__file__), "trackerdata.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                td = json.load(fh)
            break
        except Exception:
            td = None
    if not td:
        return _MAP_SUBS
    for iso, c in td.items():
        sb = (c or {}).get("sub") or {}
        terms, seen = [], set()
        for key in sb.keys():
            forms = [key]
            if key in _SUB_ALIAS:
                forms.append(_SUB_ALIAS[key])
            variants = []
            for f in forms:
                variants.append(_slugify(f)); variants.append(_strip_suffix(_slugify(f)))
            for term in variants:
                if term and len(term) >= 4 and term not in seen:
                    seen.add(term); terms.append((term, key))
        if terms:
            terms.sort(key=lambda t: -len(t[0]))   # longest first: "baja california sur" before "baja california"
            _MAP_SUBS[iso] = terms
    return _MAP_SUBS

def _map_subregion(iso, text):
    subs = _load_map_subregions().get(iso)
    if not subs:
        return ""
    t = " " + _slugify(text) + " "
    for term, key in subs:
        if (" " + term + " ") in t:
            return key
    return ""

def _subregion_for(iso, text):
    """If the map's taxonomy or the gazetteer finds a subnational region for iso, return
    it (as the exact trackerData sub key where possible)."""
    m = _map_subregion(iso, text)
    if m:
        return m
    try:
        gi, gr = _geo_tag(text)
    except Exception:
        return ""
    if gr and gi and _A2TO3.get(gi, gi) == iso:
        return gr
    return ""

_REGION_TIERS = (
    (_REGION_TERMS, 30,  True),
    (_REGION_TERMS, 90,  True),
    ("environment OR mining OR forest OR water OR pollution OR land OR energy OR dam OR deforestation", 180, True),
    ("environment OR mining OR land OR water OR development OR pollution", 365, True),
    # NOTE: no bare-name tier. A query with no topic terms returns whatever
    # merely contains the country's name -- which is how "Chad" pulled in US
    # celebrity and pipeline stories. Every tier now carries topic terms, AND
    # every kept item must independently name the region (see _region_named).
)


# --- GDELT: a global, multilingual news index built for programmatic use ---------
# Google News RSS throttles hard when queried a couple of hundred times in a run,
# which is why nearly every region came back empty while a handful of large ones
# succeeded. GDELT is designed for this access pattern, indexes non-English media,
# and needs no key -- so it becomes the primary per-region source, with Google News
# kept as a fallback.
_GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
_UA = {"User-Agent": "local-map-wire/1.0 (+wheelock.chris@gmail.com)"}
_NET = {"gdelt_ok": 0, "gdelt_fail": 0, "gnews_ok": 0, "gnews_empty": 0}


def _gdelt(name, terms, days, maxrec=20):
    """Return raw article dicts for one region, or [] on failure."""
    q = '"%s"' % name
    if terms:
        q += " (%s)" % terms
    url = _GDELT + "?" + urllib.parse.urlencode(
        {"query": q, "mode": "ArtList", "maxrecords": maxrec,
         "format": "json", "timespan": "%dd" % days, "sort": "DateDesc"})
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8", "replace")
        arts = (json.loads(raw) or {}).get("articles") or []
        _NET["gdelt_ok"] += 1
        return arts
    except Exception as e:
        _NET["gdelt_fail"] += 1
        if _NET["gdelt_fail"] <= 5:
            print("  gdelt %s failed: %s" % (name[:24], str(e)[:70]))
        return []


def _gdelt_date_ms(sd):
    try:
        return int(calendar.timegm(time.strptime(str(sd)[:15], "%Y%m%dT%H%M%S")) * 1000)
    except Exception:
        return int(time.time() * 1000)

def _gnews_url(q, days, hl="en-US", gl="US"):
    from urllib.parse import quote
    qq = q + (" when:%dd" % days if days else "")
    return ("https://news.google.com/rss/search?q=%s&hl=%s&gl=%s&ceid=%s:%s"
            % (quote(qq), hl, gl, gl, hl.split("-")[0]))


def collect_by_region(per_region=60, budget_min=None, only=None):
    """One sweep per region. GDELT first (multilingual, tolerant of this access
    pattern), Google News as fallback, widening the window until something lands.
    Failures are counted and reported rather than silently rendered as a zero."""
    import time as _t
    budget_min = budget_min or int(os.environ.get("WIRE_REGION_BUDGET_MIN", "90"))
    pace = float(os.environ.get("WIRE_PACE_SEC", "0.5"))
    t_end = _t.time() + budget_min * 60
    isos = list(only or _WIRE_REGIONS.keys())
    out, seen, empty = [], set(), []
    done = 0
    for iso in isos:
        if _t.time() > t_end:
            print("  wire regions: %d-min budget reached at %d/%d" % (budget_min, done, len(isos)))
            break
        nm = _WIRE_REGIONS.get(iso) or iso
        loc = _REGION_LOCALE.get(iso)
        done += 1
        kept = 0

        def _add(title, link, date_ms, snippet, window, subregion="", lang=""):
            key = re.sub(r"[^a-z0-9]", "", (title or "").lower())[:60]
            if not title or not link or key in seen:
                return False
            seen.add(key)
            out.append({"name": nm, "title": title[:200], "link": link, "date": date_ms,
                        "sig": 2, "snippet": (snippet or "")[:280], "iso": iso,
                        "region": subregion or "", "widened": window,
                        "lang": (lang or "").strip().title() or "Unknown"})
            return True

        for terms, days, need_match in _REGION_TIERS:
            if kept >= per_region:
                break
            for art in _gdelt(nm, terms, days, maxrec=150):
                if kept >= per_region:
                    break
                title = clean(art.get("title"))
                snip = clean(art.get("domain", ""))
                blob = title + " " + snip
                # GDELT machine-translates 65 languages and matched our English query
                # ("<country>" AND topic terms) against that TRANSLATION -- but it
                # returns the title in the ORIGINAL language. So for a non-English
                # item we can't re-read the title with our English gates; GDELT's
                # translation-side match is the authoritative signal, and its own
                # language / source-country fields tell us it belongs here. English
                # items still get the strict two-gate, because that is where the
                # person-name / same-word false positives (the "Chad" bug) live.
                lang = (art.get("language") or "").strip().lower()
                scty = (art.get("sourcecountry") or "").strip().lower()
                foreign = bool(lang) and lang not in ("english", "eng", "en")
                # source country GDELT assigns to the region we queried is corroboration
                _trust = foreign or (scty and scty == (nm or "").strip().lower())
                if _trust:
                    if _blocked(title + " " + snip):   # sport/crime/celebrity noise, any language
                        continue
                    # trust GDELT's translated match; still honor an explicit subregion
                    _sub = _subregion_for(iso, title)
                    if _add(title, art.get("url", ""), _gdelt_date_ms(art.get("seendate")),
                            snip, days, _sub, lang or "english"):
                        kept += 1
                    continue
                # English item: topic relevance AND the region must be named in the title
                if _blocked(blob):
                    continue
                if need_match and not matches(blob):
                    continue
                if not _region_named(iso, title + " " + snip):
                    continue
                _sub = _subregion_for(iso, title)         # attach a subnational region if named
                if _add(title, art.get("url", ""), _gdelt_date_ms(art.get("seendate")),
                        snip, days, _sub, lang or "english"):
                    kept += 1
            _t.sleep(pace)
            if kept >= 1:
                break

        if kept == 0:                                  # GDELT dry -> try Google News
            for terms, days, need_match in _REGION_TIERS:
                if kept >= per_region:
                    break
                urls = [_gnews_url('"%s" %s' % (nm, ("(%s)" % terms) if terms else ""), days)]
                if loc:            # add a locale-scoped query (in-country edition) when we have one
                    urls.append(_gnews_url('"%s" %s' % (nm, ("(%s)" % terms) if terms else ""),
                                           days, loc[0], loc[1]))
                for u in urls:
                    if kept >= per_region:
                        break
                    try:
                        fp = feedparser.parse(u)
                    except Exception:
                        continue
                    ents = fp.entries or []
                    if not ents:
                        _NET["gnews_empty"] += 1          # throttled or genuinely nothing
                    else:
                        _NET["gnews_ok"] += 1
                    for e in ents[:80]:
                        if kept >= per_region:
                            break
                        title = clean(e.get("title"))
                        summary = clean(e.get("summary", ""))
                        blob = title + " " + summary
                        if _blocked(blob):
                            continue
                        if need_match and not matches(blob):
                            continue
                        if not _region_named(iso, blob):
                            continue
                        ts = None
                        for k in ("published_parsed", "updated_parsed"):
                            if e.get(k):
                                try:
                                    ts = int(calendar.timegm(e[k]) * 1000); break
                                except Exception:
                                    pass
                        if _add(title, e.get("link", ""), ts or int(time.time() * 1000),
                                summary, days, _subregion_for(iso, blob), "english"):
                            kept += 1
                    _t.sleep(pace)
                if kept >= 1:
                    break

        if kept == 0:
            empty.append(iso)
        if done % 25 == 0:
            print("  wire regions: %d/%d swept, %d items, %d empty  [gdelt ok=%d fail=%d | gnews ok=%d empty=%d]"
                  % (done, len(isos), len(out), len(empty),
                     _NET["gdelt_ok"], _NET["gdelt_fail"], _NET["gnews_ok"], _NET["gnews_empty"]))
    print("  wire regions: %d items across %d swept; %d returned nothing" % (len(out), done, len(empty)))
    print("  network: gdelt ok=%d fail=%d | gnews ok=%d empty=%d"
          % (_NET["gdelt_ok"], _NET["gdelt_fail"], _NET["gnews_ok"], _NET["gnews_empty"]))
    if empty:
        print("  still empty: %s" % ",".join(empty[:40]))
    return out



def main():
    # topical pool (kept: it surfaces cross-border and movement stories), then a
    # sweep that gives every region its own query rather than a share of the pool
    items = collect()[:600]
    if os.environ.get("WIRE_SKIP_REGIONS") != "1":
        seen = set(re.sub(r"[^a-z0-9]", "", (i.get("title") or "").lower())[:60] for i in items)
        for it in collect_by_region():
            k = re.sub(r"[^a-z0-9]", "", (it.get("title") or "").lower())[:60]
            if k in seen:
                continue
            seen.add(k); items.append(it)
    # Carry forward what earlier runs found. A region that lands once stays covered
    # even if a later sweep is throttled, so coverage accumulates instead of resetting.
    if os.environ.get("WIRE_NO_MERGE") != "1" and os.path.exists("wire.json"):
        try:
            prev = json.load(open("wire.json", encoding="utf-8"))
            if isinstance(prev, list):
                have = set(re.sub(r"[^a-z0-9]", "", (i.get("title") or "").lower())[:60] for i in items)
                added = 0
                for p in prev:
                    k = re.sub(r"[^a-z0-9]", "", (p.get("title") or "").lower())[:60]
                    if k and k not in have and not _too_old(p):
                        have.add(k); items.append(p); added += 1
                print("merged %d still-current items from the previous wire" % added)
        except Exception as e:
            print("merge skipped: %s" % e)
    before = len(items)
    items = [i for i in items if not _too_old(i)]
    if len(items) != before:
        print("wire: dropped %d items older than %d days" % (before - len(items), WIRE_MAX_AGE_DAYS))
    items.sort(key=lambda i: -(i.get("date") or 0))
    cap = int(os.environ.get("WIRE_MAX_ITEMS", "9000"))
    if len(items) > cap:
        items = items[:cap]
    wide = sum(1 for i in items if (i.get("widened") or WIRE_MAX_AGE_DAYS) > WIRE_MAX_AGE_DAYS)
    covered = len(set(i.get("iso") for i in items if i.get("iso")))
    print("wire total: %d items across %d regions (base window %d days; %d found by widening)"
          % (len(items), covered, WIRE_MAX_AGE_DAYS, wide))
    for it in items:
        it.pop("score", None)
    # Safety: if too few items came back, keep the existing wire.json rather than wiping it.
    if len(items) < 4 and os.path.exists("wire.json"):
        try:
            existing = json.load(open("wire.json", encoding="utf-8"))
            if isinstance(existing, list) and len(existing) >= len(items):
                print("harvest thin (%d) -- keeping existing wire.json (%d)" % (len(items), len(existing)))
                return
        except Exception:
            pass
    # TOP-LEVEL ARRAY -- required by the map's Array.isArray() check
    with open("wire.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    print("wrote wire.json with %d items" % len(items))

if __name__ == "__main__":
    main()
