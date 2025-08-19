"""
UI Messages module for Signum labeller application
"""


def join_with_and(items, last_separator="ja"):
    """
    join_with_and takes a list of items, joins them with comma
        except the last one which is joined with last_separator parameter.
        If the last separator is "eikä" (nor), it also replaces any negatives.

    :parameter items: array the items to be joined
    :parameter last_separator:
    :return: str the resulting string

    """
    if not items:
        return ""
    elif len(items) == 1:
        return items[0]
    else:
        if last_separator == "eikä":
            last = items[-1].replace(" ei ", " ")
        else:
            last = items[-1]
        return ", ".join(items[:-1]) + f" {last_separator} " + last


def get_error_status_text(positives: list[str], negatives: list[str]):
    """
    Natural language error status text with positives first followed by negatives
    """
    return (
        f"{join_with_and(positives, 'ja')}"
        f"{", mutta " if len(positives) > 0 and len(negatives) > 0 else ""}"
        f"{join_with_and(negatives, 'eikä')}"
    ).capitalize()


# Backend status messages
BACKEND_STATUS_OK = "Yhteys ok."
BACKEND_STATUS_NO_CONNECTION = "Ei yhteyttä"
BACKEND_STATUS_ERROR = "Virhetilanne."

# Registration status message templates
REGISTRATION_STATUS_OK_TEMPLATE = "{hostname} [{ip_address}], OK"
REGISTRATION_STATUS_FAILED_TEMPLATE = "{hostname} [{ip_address}], EI OK"

# Reader status message template
READER_STATUS_TEMPLATE = "RFID-lukija, {version}"

# Item data message template
ITEM_DATA_MESSAGE_TEMPLATE = (
    "<p><h2>{best_title}</h2><h3>{best_author}</h3></p>"
    "<p><table>"
    "<tr><th align='left'>Materiaali</th><td width=30>&nbsp;</td><td>{material_name}</td></tr>"
    "<tr><th align='left'>Nidetyyppi</th><td width=10></td><td>{item_type_name}</td></tr>"
    "<tr><th align='left'>Viivakoodi</th><td width=10></td><td>{barcode}</td></tr>"
    "<tr><th align='left'>RFID ISIL</th><td width=10'></td><td>{owner_library_isil}</td></tr>"
    "<tr><th>&nbsp;</th><td width=30>&nbsp;</td><td width=30>&nbsp;</td></tr>"
    "<tr><th align='left'>Luokitus</th><td width=10p></td><td>{classification}</td></tr>"
    "<tr><th align='left'>Pääsana</th><td width=10></td><td>{shelfmark}</td></tr>"
    "</table></p>"
)

# Error message template
ERROR_MESSAGE_TEMPLATE = "<p><b>Virhe: {error}</b></p>"

# Battery low message
BATTERY_LOW_MESSAGE = (
    "<p><b>Virta vähissä!</b></p>"
    "<p>Tietokoneen akku on miltei tyhjä. Tulostus on varmuuden vuoksi kytketty pois päältä.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<p><ul><li>Käy viemässä tietokone lataukseen.</li></ul></p>"
)

# Not ready to use message template
NOT_READY_HEADER = "<p><b>Tarroja ei voi tulostaa juuri nyt.</b></p>"
NOT_READY_STATUS_TEMPLATE = "<p>{status_text}.</p>"
NOT_READY_INSTRUCTIONS_HEADER = "<p><b>Ohjeet:</b>"
NOT_READY_INSTRUCTIONS_TEMPLATE = "<ul>{fixes}</ul></p>"

# Component status messages for "not ready" state
STATUS_BACKEND_WORKING = "taustajärjestelmä toimii"
STATUS_STATION_AUTHORIZED = "asema on valtuutettu"
STATUS_RFID_CONNECTED = "RFID-lukija on yhdistetty"
STATUS_PRINTER_FOUND = "tulostin löytyy"
STATUS_BACKEND_NO_RESPONSE = "taustajärjestelmä ei vastaa"
STATUS_BACKEND_ERROR = "taustajärjestelmässä on virhe"
STATUS_NO_AUTHORIZATION = "tulostusasemalle ei saatu valtuuksia"
STATUS_RFID_NOT_CONNECTED = "RFID-lukijaa ei ole yhdistetty"
STATUS_PRINTER_NOT_FOUND = "tulostinta ei löydy"

# Fix instructions for "not ready" state
FIX_CHECK_NETWORK = "<li>Varmista, että toimipaikan verkkoyhteys toimii</li>"
FIX_REPORT_BACKEND_ERROR = (
    "<li>Pyydä toimipaikan pääkäyttäjää ilmoittamaan taustajärjestelmän virheestä</li>"
)
FIX_REQUEST_AUTHORIZATION = (
    "<li>Pyydä toimipaikan pääkäyttäjää pyytämään tarroitusasemalle valtuudet</li>"
)
FIX_CONNECT_RFID = "<li>Varmista, että RFID-lukija on yhdistetty USB-porttiin. Odota kytkemisen jälkeen hetki.</li>"
FIX_CONNECT_PRINTER = "<li>Varmista, että tulostin on yhdistetty USB-porttiin ja päällä</li>"

# Error state messages
MULTIPLE_TAGS_ERROR = (
    "<p><b>Virhetilanne</b></p>"
    "<p>Lukija havaitsee useita niteitä.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<ul><li>Varmista, että lukijan läheisyydessä ei ole muita niteitä kuin se, "
    "jota yrität tarroittaa</li></ul>"
)

UNKNOWN_TAG_ERROR = (
    "<p><b>Virhetilanne</b></p>"
    "<p>Niteessä on viallinen RFID-tagi.Se pitää vaihtaa tai aktivoida ennen "
    "signum-tarran tulostamista.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<ul><li>Laita nide syrjään. Anna vuoron lopuksi kaikki vastaavat niteet "
    "kirjastovirkailijalle. Kirjastovirkailija lähettää niteen jatkokäsittelyyn.</li></ul>"
)

BACKEND_ERROR_MESSAGE = (
    "<p><b>Virhetilanne</b></p>"
    "<p>Niteen tietoja ei saada haettua taustajärjestelmästätaustajärjestelmän "
    "palauttaman virheen vuoksi.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<ul><li>Odota vähän aikaa ja kokeile samalla tai eri niteellä uudestaan.</li></ul>"
)

BACKEND_EMPTY_RESPONSE_MESSAGE = (
    "<p><b>Virhetilanne</b></p>"
    "<p>Niteelle ei ole saatavilla tietoja taustajärjestelmässä.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<ul><li>Ilmoita tilanteesta kirjastovirkailijalle.</li></ul>"
)

READER_ERROR_MESSAGE = (
    "<p><b>Virhetilanne</b></p>"
    "<p>Lukija palauttaa virheellisiä lukutuloksia.</p>"
    "<p><b>Ohjeet:</b></p>"
    "<ul><li>Varmista, ettei lukijan läheisyydessä ole radiohäiriötä aiheuttavaa "
    "esinettä tai laitetta, esimerkiksi toista RFID-lukijaa.</li>"
    "<li>Varmista, ettei lukijan läheisyydessä ole muita niteitä kuin se, "
    "jota yrität tarroittaa</li>"
    "<li>CD, DVD ja Blu-Ray -levyt saattavat myös aiheuttaa häiriöitä. "
    "Kokeile kääntää kotelo ympäri tai liikuttaa sitä hitaasti lukijan päällä.</li></ul>"
)

# Ready to print message
READY_TO_PRINT_MESSAGE = (
    "<p><b>Valmiina tulostamaan tarroja!</b></p>"
    "<p><b>Ohjeet:</b></p>"
    "<ol><li>Aseta nide lukutason päälle</li>"
    "<li>Tulostin tulostaa tarran luettuaan niteen RFID-tunnisteen</li>"
    "<li>Kiinnitä tarra niteeseen</li></ol>"
)
ITEM_NOT_FOUND = "Nidettä ei löydy järjestelmästä"
ERROR_FETCHING_ITEM = "Virhe niteen tietojen haussa"
