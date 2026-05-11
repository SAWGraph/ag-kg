import pandas as pd

# Load CSV
df = pd.read_csv("Metadata/Crop_Category_mapping.csv")

def clean_name(value):
    """Remove spaces and handle missing values."""
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value.replace(" ", "") if value else None

triples = []

# Prefixes
triples.append("""@prefix ag: <http://w3id.org/sawgraph/v1/ag#> .
@prefix kwgr: <http://stko-kwg.geog.ucsb.edu/lod/resource/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix terms: <http://purl.org/dc/terms/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
""")

# Ontology header
triples.append("""
#################################################################
#    Ontology
#################################################################

<http://w3id.org/sawgraph/v1/ag/crop-categories> rdf:type owl:Ontology ;
                                  terms:contributor "Adrita Barua"@en ;
                                  terms:created "2025-10-20" ;
                                  terms:creator "The SAWGraph Project"@en ;
                                  terms:description "This ontology supports the SAWGraph"@en ;
                                  terms:title "Ontology for USDA's CropScape Crop Categories"@en ;
                                  owl:versionInfo "1.0"@en .
""")

# Annotation properties
triples.append("""
#################################################################
#    Annotation Properties
#################################################################

###  http://purl.org/dc/terms/contributor
terms:contributor rdf:type owl:AnnotationProperty .


###  http://purl.org/dc/terms/created
terms:created rdf:type owl:AnnotationProperty .


###  http://purl.org/dc/terms/creator
terms:creator rdf:type owl:AnnotationProperty .


###  http://purl.org/dc/terms/description
terms:description rdf:type owl:AnnotationProperty .


###  http://purl.org/dc/terms/title
terms:title rdf:type owl:AnnotationProperty .
""")

# Classes
triples.append("""
#################################################################
#    Classes
#################################################################

###  http://w3id.org/sawgraph/v1/ag#cropCategory
ag:cropCategory rdf:type owl:Class ;
                rdfs:label "Crop Category" .


###  http://w3id.org/sawgraph/v1/ag#cropSubCategory
ag:cropSubCategory rdf:type owl:Class ;
                   rdfs:subClassOf ag:cropCategory ;
                   rdfs:label "Crop Sub-Category" .
""")

# Collect unique crop categories and subcategories
crop_categories = set()
crop_subcategories = set()

for _, row in df.iterrows():
    crop_category = clean_name(row[2])
    crop_subcategory = clean_name(row[3])

    if crop_category:
        crop_categories.add(crop_category)

    if crop_subcategory:
        crop_subcategories.add(crop_subcategory)

# Crop category individuals
triples.append("""
#################################################################
#    Individuals — Crop Categories
#################################################################
""")

for category in sorted(crop_categories):
    triples.append(f"""###  http://w3id.org/sawgraph/v1/ag#cropCategory.{category}
ag:cropCategory.{category} rdf:type owl:NamedIndividual ,
                                  ag:cropCategory ;
                         rdfs:label "Crop Category for {category}"^^xsd:string .
""")

# Crop subcategory individuals
triples.append("""
#################################################################
#    Individuals — Crop Sub-Categories
#################################################################
""")

for subcat in sorted(crop_subcategories):
    triples.append(f"""###  http://w3id.org/sawgraph/v1/ag#cropSubCategory.{subcat}
ag:cropSubCategory.{subcat} rdf:type owl:NamedIndividual ,
                                     ag:cropSubCategory ;
                            rdfs:label "Crop Sub Category for {subcat}"^^xsd:string .
""")

# Crop category assignments
triples.append("""
#################################################################
#    Crop Category & Sub-Category Assignments
#################################################################
""")

for _, row in df.iterrows():
    obs_id = str(row[0]).strip()
    crop_category = clean_name(row[2])
    crop_subcategory = clean_name(row[3])

    if not obs_id or obs_id.lower() == "nan":
        continue

    subject = f"kwgr:croplandObservableProperty.{obs_id}"

    if crop_category and crop_subcategory:
        triples.append(f"""###  http://stko-kwg.geog.ucsb.edu/lod/resource/croplandObservableProperty.{obs_id}
{subject} ag:hasCropCategory ag:cropCategory.{crop_category} ;
{' ' * (len(subject) + 1)}ag:hasCropSubCategory ag:cropSubCategory.{crop_subcategory} .
""")

    elif crop_category:
        triples.append(f"""###  http://stko-kwg.geog.ucsb.edu/lod/resource/croplandObservableProperty.{obs_id}
{subject} ag:hasCropCategory ag:cropCategory.{crop_category} .
""")

    elif crop_subcategory:
        triples.append(f"""###  http://stko-kwg.geog.ucsb.edu/lod/resource/croplandObservableProperty.{obs_id}
{subject} ag:hasCropSubCategory ag:cropSubCategory.{crop_subcategory} .
""")

# Write to TTL file
output_file = "crop_category_triples.ttl"

with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(triples))

print(f"✅ RDF triples successfully generated and saved to '{output_file}'")
