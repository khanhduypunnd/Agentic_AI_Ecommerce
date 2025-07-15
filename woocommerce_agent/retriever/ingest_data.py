import pandas as pd
import numpy as np
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import create_client
import os
from dotenv import load_dotenv
import math

# def normalize_storage(value):
#     value = str(value).strip().upper().replace(' ', '')
#     if 'TB' in value:
#         try:
#             number = float(value.replace('TB', ''))
#             return int(number * 1024)
#         except:
#             return 0
#     elif 'GB' in value:
#         try:
#             number = float(value.replace('GB', ''))
#             return int(number)
#         except:
#             return 0
#     else:
#         try:
#             # Trường hợp đã là số đơn thuần (giả sử là GB)
#             return int(value)
#         except:
#             return 0
        
def preprocess_data(df: pd.DataFrame) -> pd.DataFrame:
    """Tiền xử lý dữ liệu để tối ưu hóa cho vector hóa"""
    # Chuẩn hóa dữ liệu số và categorical
    # df['price'] = df['price'].astype(float)
    # df['ram'] = df['ram'].fillna('').apply(lambda x: str(x).replace('GB', '').strip().replace(' ', ''))
    # df['storage'] = df['storage'].fillna('').apply(normalize_storage)
    
    # Xử lý giá trị thiếu
    text_columns = ['name', 'description']
    for col in text_columns:
        df[col] = df[col].fillna('')
    
    # Chuẩn hóa đánh giá
    # df['evaluate'] = df['evaluate'].apply(lambda x: f"{x}/5" if isinstance(x, (int, float)) else x)
    
    return df

def generate_product_content(row: pd.Series) -> str:
    """Tạo nội dung semantic-rich cho embedding từ các trường sản phẩm"""
    features = [
        f"**Sản phẩm**: {row['name']}",
        f"**Mô tả**: {row['description']}",
    ]
    return "\n".join(features)

def clean_metadata(metadata):
        for k, v in metadata.items():
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    metadata[k] = None  
        return metadata

def load_to_supabase(excel_path: str):
    # Đọc và tiền xử lý dữ liệu
    df = pd.read_excel(excel_path)
    df = preprocess_data(df)
    
    docs = []
    for _, row in df.iterrows():
        # Tạo nội dung semantic cho embedding
        content = generate_product_content(row)
        
        # Tạo metadata với các trường filterable
        metadata = {
            "brand": row["brand"],
            "name": row["name"],
            "option": row["option"],
            "price": float(row["price"]),
            "description": row["description"],
            "stock_status": row["stock_status"],
            "permalink": row["permalink"],
            "image": row["image"],
            "categories": row["categories"],
        }
        
        docs.append(Document(page_content=content, metadata= clean_metadata(metadata)))

    # Kết nối Supabase
    load_dotenv()
    client = create_client(
        supabase_url=os.getenv("SUPABASE_URL"),
        supabase_key=os.getenv("SUPABASE_SERVICE_KEY")
    )

    # Khởi tạo embedding model (tối ưu cho tiếng Việt)
    embed = HuggingFaceEmbeddings(
        model_name="Alibaba-NLP/gte-multilingual-base",
        model_kwargs={'device':'cuda', 'trust_remote_code': True}
    )

    # Tải dữ liệu lên Supabase
    vector_store = SupabaseVectorStore.from_documents(
        documents=docs,
        embedding=embed,
        client=client,
        table_name="products",
        query_name="match_documents"
    )
    
    print(f"[SUCCESS] Đã nạp {len(docs)} sản phẩm lên Supabase")
    print(f"[NOTE] Kích thước vector: {len(embed.embed_query('test'))} chiều")

if __name__ == "__main__":
    load_to_supabase("meta_data.xlsx")

