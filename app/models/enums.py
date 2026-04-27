from enum import Enum


class DocType(str, Enum):
    hcl = "hcl"
    dispozitie_primar = "dispozitie_primar"
    act_normativ_local = "act_normativ_local"
    proiect_hotarare = "proiect_hotarare"
    regulament = "regulament"
    buget = "buget"
    raport_executie_bugetara = "raport_executie_bugetara"
    pug = "pug"
    puz = "puz"
    strategie = "strategie"
    organigrama = "organigrama"
    raport_activitate = "raport_activitate"
    proces_verbal = "proces_verbal"
    consultare_publica = "consultare_publica"
    anunt_public = "anunt_public"
    anunt_achizitie = "anunt_achizitie"
    declaratie_avere = "declaratie_avere"
    other = "other"


class ContentType(str, Enum):
    html = "html"
    pdf = "pdf"
    docx = "docx"
    xlsx = "xlsx"
    image = "image"
    other = "other"


class CrawlStatus(str, Enum):
    queued = "queued"
    fetching_sitemap = "fetching_sitemap"
    crawling = "crawling"
    extracting = "extracting"
    classifying = "classifying"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"
    partial = "partial"


class RenderMode(str, Enum):
    always = "always"
    never = "never"
    auto = "auto"