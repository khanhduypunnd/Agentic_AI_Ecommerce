from retrieval import get_product_semantic, query_supabase

result = query_supabase("SELECT metadata FROM products WHERE (metadata->>'brand')::text = 'Calvin Klein' AND (metadata->>'price')::int BETWEEN 100000 AND 500000")
print(result)
