# retrieval.py
from langchain_community.vectorstores import SupabaseVectorStore
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv
import os
from supabase.client import create_client
load_dotenv()

client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

def query_supabase(sql_query):
    """
    Thực thi một truy vấn SQL trên Supabase và tự động wrap kết quả vào JSONB.

    Tham số:
        sql_query (str): Câu lệnh SQL cần thực thi.

    Trả về:
        str: Chuỗi kết quả đã được định dạng để LLM dễ xử lý.
    """
    X = 4
    sql_query = sql_query.strip().rstrip(';')
    if 'limit' not in sql_query.lower():
        sql_query += f' LIMIT {X}'

    wrapped_query = f"SELECT to_jsonb(t) FROM ({sql_query}) AS t;"

    try:
        response = client.postgrest.rpc('execute_sql', {"sql": wrapped_query}).execute()

        data = response.data
        if getattr(response, "error", None) is None:
            if not data:
                return "Không tìm thấy kết quả phù hợp."

            output = f"TÌM THẤY {len(data)} KẾT QUẢ:\n"
            for idx, row in enumerate(data):
                # Xử lý cả hai trường hợp:
                item = row 

                if not item:
                    output += f"\nKẾT QUẢ {idx+1}: (Không có dữ liệu)\n"
                    continue

                output += f"\nKẾT QUẢ {idx+1}:\n"
                for key, value in item.items():
                    output += f"- {key}: {value}\n"
            return output
        else:
            return f"Lỗi truy vấn: {response.error.get('message', 'Không rõ lỗi')}"
    except Exception as e:
        return f"Lỗi hệ thống: {str(e)}"

def get_vector_retriever(embedding_model):
    """
    Return a LangChain VectorStoreRetriever instance that can be used to retrieve
    product information from Supabase using a vector store.

    Args:
        embedding_model: An instance of HuggingFaceEmbeddings (or compatible) đã được load sẵn.

    Returns:
        langchain.VectorStoreRetriever: A VectorStoreRetriever instance that can
            be used to retrieve product information from Supabase.
    """
    vs = SupabaseVectorStore(
        client=client,
        embedding=embedding_model, 
        table_name="products",
        query_name="match_documents"
    )
    return vs.as_retriever(search_kwargs={"k": 3})

def get_product_semantic(query, embedding_model):
    """
    Truy xuất thông tin ngữ nghĩa của sản phẩm dựa trên truy vấn.

    Tham số:
        query (str): Câu truy vấn để tìm các sản phẩm liên quan.
        embedding_model: Một instance của HuggingFaceEmbeddings.

    Trả về:
        str: Chuỗi đã được định dạng tóm tắt tổng số sản phẩm tìm thấy 
        và chi tiết metadata của chúng.
    """

    retriever = get_vector_retriever(embedding_model)
    docs_res = retriever.invoke(query)
    total_docs = len(docs_res)
    output = f"TÌM THẤY TỔNG CỘNG {total_docs} SẢN PHẨM"
    for idx, doc in enumerate(docs_res):
        output += f"\n\nSẢN PHẨM {idx+1}:\n"
        metadata_str = "\n".join(f"{key}: {value}" for key, value in doc.metadata.items())
        output += metadata_str
    return output