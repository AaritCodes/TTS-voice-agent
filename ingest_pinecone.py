# ingest_pinecone.py
import os
import re
import requests
from pypdf import PdfReader
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

# Configure APIs
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable is not set!")

pinecone_api_key = os.getenv("PINECONE_API_KEY")
if not pinecone_api_key:
    raise ValueError("PINECONE_API_KEY environment variable is not set!")
pc = Pinecone(api_key=pinecone_api_key)

index_name = os.getenv("PINECONE_INDEX_NAME", "voice-agent-kb")
target_dimension = 3072  # gemini-embedding-001 returns 3072 dimensions

# Setup Pinecone index
def get_or_create_index():
    indexes = pc.list_indexes().names()
    
    if index_name in indexes:
        # Check if the existing index has the correct dimension
        desc = pc.describe_index(index_name)
        if desc.dimension != target_dimension:
            print(f"Index '{index_name}' exists but has dimension {desc.dimension}. Deleting it to recreate with {target_dimension}...")
            pc.delete_index(index_name)
            indexes = pc.list_indexes().names()
            
    if index_name not in indexes:
        print(f"Creating Pinecone index '{index_name}' with dimension {target_dimension}...")
        pc.create_index(
            name=index_name,
            dimension=target_dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
    return pc.Index(index_name)

def get_embedding(text):
    # Call Gemini Embeddings API directly via HTTP REST to bypass gRPC credential scope limitations
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
    payload = {
        "model": "models/gemini-embedding-001",
        "content": {
            "parts": [{
                "text": text
            }]
        }
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        return response.json()["embedding"]["values"]
    else:
        raise Exception(f"Gemini API Error: {response.text}")

def extract_and_chunk_pdf(pdf_path):
    print(f"Reading: {pdf_path}...")
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"
            
    # Chunk text by paragraphs (splitting by double-newline or multiple spaces)
    raw_chunks = re.split(r'\n\s*\n', full_text)
    chunks = []
    
    for c in raw_chunks:
        c_clean = c.strip()
        # Filter out extremely short or trivial lines
        if len(c_clean) > 30:
            # Clean up excessive internal whitespace/newlines
            c_clean = re.sub(r'\s+', ' ', c_clean)
            chunks.append(c_clean)
            
    return chunks

def ingest_pdf(pdf_path, index, file_id_prefix):
    if not os.path.exists(pdf_path):
        print(f"Warning: File not found: {pdf_path}")
        return
        
    chunks = extract_and_chunk_pdf(pdf_path)
    print(f"Found {len(chunks)} chunks in {pdf_path}")
    
    vectors_to_upsert = []
    
    for i, chunk in enumerate(chunks):
        print(f"  [{file_id_prefix}] Embedding chunk {i+1}/{len(chunks)}...")
        try:
            embedding = get_embedding(chunk)
            vectors_to_upsert.append({
                "id": f"{file_id_prefix}_chunk_{i}",
                "values": embedding,
                "metadata": {
                    "text": chunk,
                    "source": os.path.basename(pdf_path)
                }
            })
        except Exception as e:
            print(f"  Error embedding chunk {i}: {e}")
            
    if vectors_to_upsert:
        print(f"Upserting {len(vectors_to_upsert)} vectors to Pinecone index '{index_name}'...")
        index.upsert(vectors=vectors_to_upsert)
        print(f"Ingestion for {pdf_path} complete!")
    else:
        print("Warning: No vectors to ingest.")

if __name__ == "__main__":
    index = get_or_create_index()
    
    # Ingest the Brother Support Guide
    ingest_pdf(
        "Brother_Customer_Support_Knowledge_Base (1) (1).pdf", 
        index, 
        "brother_support"
    )
    
    # Ingest the voice assistant meeting notes / testing notes
    ingest_pdf(
        "Quick Connect - Voice Bot test - 2026_06_09 16_31 IST - Notes by Gemini.pdf", 
        index, 
        "gemini_test_notes"
    )
    
    print("\nAll database ingestions completed successfully!")
