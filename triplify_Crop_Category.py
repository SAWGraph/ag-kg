import pandas as pd

# Load CSV
df = pd.read_csv("Crop_Category_mapping.csv")

# Define prefixes
prefixes = """@prefix ag: <http://w3id.org/sawgraph/v1/ag#> .
@prefix kwgr: <http://w3id.org/sawgraph/v1/kwgr#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

"""

triples = [prefixes]

# Collect unique crop categories and subcategories
crop_categories = set()
crop_subcategories = set()

for _, row in df.iterrows():
    crop_category = str(row[2]).strip() if pd.notna(row[2]) else None
    crop_subcategory = str(row[3]).strip() if pd.notna(row[3]) else None

    if crop_category:
        crop_categories.add(crop_category.replace(" ", ""))
    if crop_subcategory:
        crop_subcategories.add(crop_subcategory.replace(" ", ""))

# Define all unique crop categories
for category in sorted(crop_categories):
    triples.append(f"ag:cropCategory.{category} a ag:cropCategory,")
    triples.append("        owl:NamedIndividual ;")
    triples.append(f'    rdfs:label "Crop Category for {category}"^^xsd:string .\n')

# Define all unique crop subcategories
for subcat in sorted(crop_subcategories):
    triples.append(f"ag:cropSubCategory.{subcat} a ag:cropSubCategory,")
    triples.append("        owl:NamedIndividual ;")
    triples.append(f'    rdfs:label "Crop Sub Category for {subcat}"^^xsd:string .\n')

# Add the class definitions (as in your example)
triples.append("ag:cropCategory rdf:type owl:Class ;")
triples.append('                         rdfs:label "Crop Category" .\n')

triples.append("ag:cropSubCategory rdf:type owl:Class ;")
triples.append('                         rdfs:label "Crop Sub-Category" ;')
triples.append("		   rdfs:subClassOf ag:cropCategory .\n")

# Generate triples for each observable property
for _, row in df.iterrows():
    obs_id = str(row[0]).strip()
    crop_category = str(row[2]).strip() if pd.notna(row[2]) else None
    crop_subcategory = str(row[3]).strip() if pd.notna(row[3]) else None

    # Skip if no observable property ID
    if not obs_id:
        continue

    # Build property triple
    property_triple = f"kwgr:croplandObservableProperty.{obs_id}"

    relations = []
    if crop_category:
        relations.append(f"ag:hasCropCategory ag:cropCategory.{crop_category.replace(' ', '')}")
    if crop_subcategory:
        relations.append(f"ag:hasCropSubCategory ag:cropSubCategory.{crop_subcategory.replace(' ', '')}")

    # Only write if there's at least one valid relation
    if relations:
        triples.append(f"{property_triple} " + " ;\n                                 ".join(relations) + " .\n")

# Write to TTL file
with open("crop_triples.ttl", "w") as f:
    f.write("\n".join(triples))

print("✅ RDF triples successfully generated and saved to 'crop_category_triples.ttl'")


