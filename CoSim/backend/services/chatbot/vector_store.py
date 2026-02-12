"""
RAG Vector Database Service for CoSim Chatbot
Creates and manages embeddings for product documentation
"""
import os
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from redis_cache import (
    acquire_warmup_lock,
    cache_query_results,
    get_cached_query_results,
    is_vector_ready,
    mark_vector_ready,
    release_warmup_lock,
    wait_for_vector_ready,
)


class RAGVectorStore:
    """Manages vector embeddings for product documentation"""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """Initialize ChromaDB and embedding model"""
        self.persist_directory = persist_directory
        
        # Initialize ChromaDB with persistence
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            anonymized_telemetry=False
        ))
        
        # Load sentence transformer model for embeddings
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="cosim_product_docs",
            metadata={"description": "CoSim product documentation and features"}
        )
    
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks for better retrieval"""
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), chunk_size - overlap):
            chunk = ' '.join(words[i:i + chunk_size])
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def load_product_docs(self, docs_path: str = "./product_docs.txt"):
        """Load and index product documentation"""
        # Read documentation
        with open(docs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split into sections by headers
        sections = []
        current_section = {"title": "Introduction", "content": ""}
        
        for line in content.split('\n'):
            if line.startswith('##'):
                # Save previous section
                if current_section["content"].strip():
                    sections.append(current_section)
                # Start new section
                current_section = {
                    "title": line.replace('##', '').strip(),
                    "content": ""
                }
            else:
                current_section["content"] += line + "\n"
        
        # Add last section
        if current_section["content"].strip():
            sections.append(current_section)
        
        # Process and add to vector store
        documents = []
        metadatas = []
        ids = []
        
        for idx, section in enumerate(sections):
            # Chunk the section content
            chunks = self.chunk_text(section["content"], chunk_size=300, overlap=50)
            
            for chunk_idx, chunk in enumerate(chunks):
                if len(chunk.strip()) < 50:  # Skip very short chunks
                    continue
                
                doc_id = f"doc_{idx}_{chunk_idx}"
                documents.append(chunk)
                metadatas.append({
                    "section": section["title"],
                    "chunk_index": chunk_idx,
                    "total_chunks": len(chunks)
                })
                ids.append(doc_id)
        
        # Add to collection
        if documents:
            # Add in batches to avoid memory issues
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                batch_docs = documents[i:i + batch_size]
                batch_meta = metadatas[i:i + batch_size]
                batch_ids = ids[i:i + batch_size]
                
                self.collection.add(
                    documents=batch_docs,
                    metadatas=batch_meta,
                    ids=batch_ids
                )
        
        print(f"✅ Indexed {len(documents)} document chunks from {len(sections)} sections")
    
    def add_faq_data(self):
        """Add common FAQ entries to the vector store"""
        faqs = [
            {
                "question": "How do I get started with CoSim?",
                "answer": "To get started: 1) Sign up for a free account, 2) Create your first project, 3) Choose a template (RL, SLAM, or Empty), 4) Launch a workspace session, and 5) Start coding in the browser. Your simulation will appear in real-time."
            },
            {
                "question": "What simulators does CoSim support?",
                "answer": "CoSim currently supports MuJoCo 3 (with optional MJX GPU acceleration) and PyBullet physics simulation. Both simulators stream via WebRTC for low-latency viewing."
            },
            {
                "question": "Can I use GPUs for training?",
                "answer": "Yes! CoSim offers GPU support for RL training. You can request GPU allocation when creating a training job. We support NVIDIA A10, 3090, and Ada GPUs. The free tier is CPU-only, but Student and Pro tiers include GPU access."
            },
            {
                "question": "How does collaboration work?",
                "answer": "CoSim uses Yjs CRDT technology for real-time collaboration. Multiple users can edit the same code files simultaneously, see each other's cursors, and view the same simulation. It's like Google Docs for robotics code."
            },
            {
                "question": "What programming languages are supported?",
                "answer": "CoSim provides first-class support for both C++ (with clang/gcc, CMake, gdb/lldb debugging) and Python (with virtual environments, pip/poetry). You can also work with mixed C++/Python projects."
            },
            {
                "question": "How much does CoSim cost?",
                "answer": "Free tier: CPU-only, 2 vCPU/4GB RAM, 20 hours/month, 2GB storage. Student tier: 4 vCPU/8GB RAM, optional GPU minutes, 10GB storage. Pro tier: Adjustable resources, unlimited hours, GPU access. Teams/Enterprise: Custom allocation and SSO."
            },
            {
                "question": "Can I run SLAM experiments?",
                "answer": "Yes! CoSim has a dedicated SLAM agent. You can upload datasets (KITTI, TUM formats), run pipelines like ORB-SLAM2, and automatically compute metrics like ATE and RPE. Rosbag playback is also supported."
            },
            {
                "question": "How do I train RL agents?",
                "answer": "Create an RL job with your algorithm (PPO, SAC, etc.), configure parallel environments, and optionally request GPU. CoSim handles the orchestration, saves checkpoints to S3, and streams TensorBoard for monitoring."
            },
            {
                "question": "Is my code and data secure?",
                "answer": "Yes. CoSim uses isolated Kubernetes namespaces per session, mTLS for services, JWT authentication, KMS-encrypted secrets, and network policies. All data is encrypted at rest and in transit."
            },
            {
                "question": "Can I snapshot my workspace?",
                "answer": "Yes! You can take snapshots of your entire workspace including code, environment lockfiles, and data references. Snapshots can be restored to new sessions for reproducibility."
            },
            {
                "question": "What happens if my session is idle?",
                "answer": "CoSim automatically hibernates idle sessions after 5 minutes of inactivity to save costs. Your work is saved, and you can resume anytime. RL/SLAM jobs checkpoint every 5-10 minutes."
            },
            {
                "question": "Can I use this for teaching?",
                "answer": "Absolutely! CoSim is built for education. Features include roster sync, automatic grading, public templates, and no local setup required for students. Perfect for robotics and ML courses."
            }
        ]
        
        documents = []
        metadatas = []
        ids = []
        
        for idx, faq in enumerate(faqs):
            # Add question-answer pair as a single document
            doc = f"Q: {faq['question']}\nA: {faq['answer']}"
            documents.append(doc)
            metadatas.append({
                "section": "FAQ",
                "question": faq["question"]
            })
            ids.append(f"faq_{idx}")
        
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        print(f"✅ Added {len(faqs)} FAQ entries")
    
    def query(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """Query the vector store for relevant documents"""
        cached = get_cached_query_results(query_text, n_results)
        if cached is not None:
            return cached

        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        
        # Format results
        formatted_results = []
        if results and results['documents']:
            for i in range(len(results['documents'][0])):
                formatted_results.append({
                    "content": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                    "distance": results['distances'][0][i] if results['distances'] else None
                })
        
        cache_query_results(query_text, n_results, formatted_results)

        return formatted_results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store"""
        count = self.collection.count()
        return {
            "total_documents": count,
            "collection_name": self.collection.name,
            "persist_directory": self.persist_directory
        }


def initialize_vector_store():
    """Initialize and populate the vector store"""
    print("🚀 Initializing RAG Vector Store...")

    store = RAGVectorStore()

    stats = store.get_stats()
    if stats["total_documents"] > 0:
        print(f"✅ Vector store already initialized with {stats['total_documents']} documents")
        mark_vector_ready()
        return store

    if not acquire_warmup_lock():
        print("⏳ Waiting for existing vector store warmup...")
        wait_for_vector_ready()
        return store

    try:
        print("📚 Loading product documentation...")
        docs_path = Path(__file__).parent / "product_docs.txt"
        store.load_product_docs(str(docs_path))

        print("❓ Adding FAQ entries...")
        store.add_faq_data()

        stats = store.get_stats()
        print(f"\n✅ Vector store initialized successfully!")
        print(f"   Total documents: {stats['total_documents']}\n   Persist directory: {stats['persist_directory']}")
        mark_vector_ready()
    finally:
        release_warmup_lock()

    return store


if __name__ == "__main__":
    # Test the vector store
    store = initialize_vector_store()
    
    # Test queries
    test_queries = [
        "How do I get started?",
        "What simulators are supported?",
        "Can I use GPUs?",
        "Tell me about collaboration features"
    ]
    
    print("\n🔍 Testing queries...")
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = store.query(query, n_results=2)
        for i, result in enumerate(results, 1):
            print(f"  Result {i} (distance: {result['distance']:.3f}):")
            print(f"    Section: {result['metadata'].get('section', 'N/A')}")
            print(f"    Content: {result['content'][:100]}...")
