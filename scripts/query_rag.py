"""
Query the Graph RAG Engine

Usage:
    python scripts/query_rag.py "What was I debugging yesterday?"
    python scripts/query_rag.py --related redis
    python scripts/query_rag.py --stats
"""

import sys
import argparse

sys.path.insert(0, '.')

from core.rag.engine import GraphRAGEngine


def main():
    parser = argparse.ArgumentParser(description="Query Mnemosyne Graph RAG")
    parser.add_argument("query", nargs="?", help="Natural language query")
    parser.add_argument("--related", type=str, help="Find related entities")
    parser.add_argument("--stats", action="store_true", help="Show engine stats")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results")
    
    args = parser.parse_args()
    
    # Initialize engine
    engine = GraphRAGEngine()
    
    # Load persisted graph if exists
    from pathlib import Path
    graph_path = Path(".mnemosyne/knowledge_graph.json")
    engine.load_graph(graph_path)
    
    if args.stats:
        print("\n" + "=" * 50)
        print("📊 Graph RAG Engine Stats")
        print("=" * 50)
        stats = engine.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")
        print("=" * 50)
        return
    
    if args.related:
        print(f"\n🔗 Finding entities related to '{args.related}'...")
        results = engine.find_related(args.related)
        
        if not results:
            print("  No related entities found.")
        else:
            for r in results:
                print(f"  [{r['type']}] {r['node']} (from {r['from']})")
        return
    
    if args.query:
        print(f"\n🔍 Searching: '{args.query}'...")
        results = engine.query(args.query, top_k=args.top_k)
        
        if not results:
            print("  No results found.")
            print("  (Have you indexed any sessions?)")
        else:
            print(f"\nFound {len(results)} results:\n")
            for i, r in enumerate(results, 1):
                print(f"─" * 50)
                print(f"#{i} | Score: {r['score']:.3f}")
                print(f"{r['text'][:200]}...")
                if r.get('metadata'):
                    print(f"Metadata: {r['metadata']}")
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
