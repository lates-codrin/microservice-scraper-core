from app.models.enums import DocType
from app.services.classifier import classify_document
from app.services.field_extractor import extract_hcl_fields


def test_classifier_all_slugs():
    # 18 slugs, URL match mostly, plus some keywords
    cases = [
        ("http://x/hcl/1", "hotarare consiliul local", DocType.hcl, 0.94),
        ("http://x/dispozitii/", "dispozitie primar", DocType.dispozitie_primar, 0.94),
        ("http://x/acte-normative/", "act normativ", DocType.act_normativ_local, 0.94),
        ("http://x/proiecte/", "proiect de hotarare", DocType.proiect_hotarare, 0.94),
        ("http://x/regulamente/", "regulament", DocType.regulament, 0.94),
        ("http://x/buget/", "buget local", DocType.buget, 0.94),
        ("http://x/executie/", "executie bugetara", DocType.raport_executie_bugetara, 0.94),
        ("http://x/pug/", "plan urbanistic general", DocType.pug, 0.94),
        ("http://x/puz/", "puz", DocType.puz, 0.94),
        ("http://x/strategii/", "strategie", DocType.strategie, 0.94),
        ("http://x/organigrama/", "organigrama", DocType.organigrama, 0.94),
        ("http://x/rapoarte/", "raport de activitate", DocType.raport_activitate, 0.94),
        ("http://x/procese-verbale/", "proces verbal", DocType.proces_verbal, 0.94),
        ("http://x/consultare/", "consultare publica", DocType.consultare_publica, 0.94),
        ("http://x/anunturi/", "anunt public", DocType.anunt_public, 0.94),
        ("http://x/achizitii/", "achizitie", DocType.anunt_achizitie, 0.94),
        ("http://x/declaratii/", "declaratie de avere", DocType.declaratie_avere, 0.94),
        ("http://x/random/", "nimic", DocType.other, 0.40),
    ]
    for url, text, expected_type, expected_conf in cases:
        dtype, conf, alts = classify_document(url, text)
        assert dtype == expected_type
        assert conf == expected_conf


def test_extract_hcl():
    text = "Hotararea nr. 125/2024 din 22.04.2024 privind aprobarea bugetului local.\nVoturi: pentru: 13, \u00eempotriv\u0103: 2, ab\u021bineri: 1."
    fields, conf = extract_hcl_fields(text)
    assert fields["hcl_number"] == "125/2024"
    assert fields["adoption_date"] == "2024-04-22"
    assert fields["subject"] == "aprobarea bugetului local"
    assert fields["votes"] == {"for": 13, "against": 2, "abstain": 1}
    assert conf["hcl_number"] == 0.99
