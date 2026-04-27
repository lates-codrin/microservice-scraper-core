import re
from typing import Any, Tuple, List, Dict
from app.models.enums import DocType

URL_PATTERNS = {
    "/hcl/": DocType.hcl,
    "/hotarari/": DocType.hcl,
    "/dispozitii/": DocType.dispozitie_primar,
    "/proiecte/": DocType.proiect_hotarare,
    "/regulamente/": DocType.regulament,
    "/buget/": DocType.buget,
    "/pug/": DocType.pug,
    "/puz/": DocType.puz,
    "/strategii/": DocType.strategie,
    "/organigrama/": DocType.organigrama,
    "/rapoarte/": DocType.raport_activitate,
    "/procese-verbale/": DocType.proces_verbal,
    "/consultare/": DocType.consultare_publica,
    "/achizitii/": DocType.anunt_achizitie,
    "/declaratii/": DocType.declaratie_avere,
    "/anunturi/": DocType.anunt_public,
    "/executie/": DocType.raport_executie_bugetara,
    "/acte-normative/": DocType.act_normativ_local,
}

KEYWORDS = {
    DocType.hcl: ["hotarare", "hotărâre", "consiliul local"],
    DocType.dispozitie_primar: ["dispozitie", "dispoziție", "primar"],
    DocType.act_normativ_local: ["act normativ"],
    DocType.proiect_hotarare: ["proiect de hotarare", "proiect de hotărâre"],
    DocType.regulament: ["regulament"],
    DocType.buget: ["buget local", "bugetului local"],
    DocType.raport_executie_bugetara: ["executie bugetara", "execuție bugetară"],
    DocType.pug: ["plan urbanistic general", "pug"],
    DocType.puz: ["plan urbanistic zonal", "puz"],
    DocType.strategie: ["strategie", "dezvoltare"],
    DocType.organigrama: ["organigrama", "organigramă"],
    DocType.raport_activitate: ["raport de activitate"],
    DocType.proces_verbal: ["proces verbal"],
    DocType.consultare_publica: ["consultare publica", "consultare publică", "dezbatere"],
    DocType.anunt_public: ["anunt", "anunț"],
    DocType.anunt_achizitie: ["achizitie", "achiziție", "licitatie", "licitație"],
    DocType.declaratie_avere: ["declaratie de avere", "declarație de avere", "interese"],
}

def classify_document(url: Any | None, text: str) -> Tuple[DocType, float, List[Dict[str, Any]]]:
    url_match = None
    if url:
        url_lower = str(url).lower()
        for pattern, dtype in URL_PATTERNS.items():
            if pattern in url_lower:
                url_match = dtype
                break
                
    text_lower = text.lower()
    keyword_scores = {dtype: 0 for dtype in DocType if dtype != DocType.other}
    
    for dtype, words in KEYWORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\b", text_lower):
                keyword_scores[dtype] += len(w)
                
    sorted_scores = sorted(keyword_scores.items(), key=lambda x: x[1], reverse=True)
    text_match = sorted_scores[0][0] if sorted_scores and sorted_scores[0][1] > 0 else None
    
    confidence = 0.40
    doc_type = DocType.other
    
    if url_match and text_match and url_match == text_match:
        doc_type = url_match
        confidence = 0.94
    elif text_match:
        doc_type = text_match
        confidence = 0.80
    elif url_match:
        doc_type = url_match
        confidence = 0.75
        
    alts = []
    for dtype, score in sorted_scores:
        if dtype != doc_type and score > 0:
            alts.append({"doc_type": dtype, "confidence": min(0.5, score * 0.1)})
    
    return doc_type, confidence, alts[:2]

def extract_hcl_fields(text: str) -> Tuple[Dict[str, Any], Dict[str, float]]:
    fields = {"hcl_number": None, "adoption_date": None, "subject": None, "votes": None}
    conf = {}
    
    text_lower = text.lower()
    
    m_num = re.search(r"(\d+/\d{4})", text)
    if m_num:
        fields["hcl_number"] = m_num.group(1)
        conf["hcl_number"] = 0.99
        
    m_date = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    if m_date:
        parts = m_date.group(1).split('.')
        fields["adoption_date"] = f"{parts[2]}-{parts[1]}-{parts[0]}"
        conf["adoption_date"] = 0.90
        
    m_subj = re.search(r"privind\s+([^\.]+)", text, re.IGNORECASE)
    if m_subj:
        fields["subject"] = m_subj.group(1).strip()
        conf["subject"] = 0.85
        
    m_votes = re.search(r"pentru:\s*(\d+).*?împotrivă:\s*(\d+).*?abțineri:\s*(\d+)", text, re.IGNORECASE)
    if m_votes:
        fields["votes"] = {
            "for": int(m_votes.group(1)),
            "against": int(m_votes.group(2)),
            "abstain": int(m_votes.group(3))
        }
        conf["votes"] = 0.95
        
    return fields, conf
