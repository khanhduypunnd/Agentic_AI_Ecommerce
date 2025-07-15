-- 1. Kích hoạt pgvector extension
create extension if not exists vector;

-- 2. Tạo bảng lưu sản phẩm với nội dung, metadata và embedding
create table products (
  id uuid primary key default gen_random_uuid(),
  content text not null,           -- tương ứng với Document.page_content
  metadata jsonb not null,         -- lưu thông tin metadata (name, brand, …)
  embedding vector(768) not null   -- dimension phụ thuộc model, ví dụ HuggingFace gte-multilingual-base là 768-dims
);

-- Chỉ cần chạy 1 lần
create index products_embedding_idx
on products
using ivfflat (embedding vector_cosine_ops)
with (lists = 100);

-- 3. Tạo function để tìm kiếm sản phẩm tương tự
create or replace function match_documents(
  query_embedding vector(768),
  match_count int default null,
  filter jsonb default '{}'
) returns table (
  id uuid,
  content text,
  metadata jsonb,
  similarity float
) language plpgsql as $$
#variable_conflict use_column
begin
  return query
    select
      products.id,
      products.content,
      products.metadata,
      1 - (products.embedding <=> query_embedding) as similarity
    from products
    where metadata @> filter
    order by products.embedding <=> query_embedding
    limit match_count;
end;
$$;
