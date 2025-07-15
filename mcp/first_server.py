from mcp.server.fastmcp import FastMCP
# import getdotenv
from dotenv import load_dotenv
import os
import requests
from requests.auth import HTTPBasicAuth
import re
import unicodedata
from urllib.parse import unquote 
# from tavily import TavilyClient
from bs4 import BeautifulSoup
    
load_dotenv()

CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")

# Create an MCP server
mcp = FastMCP("Muse", port=8001)

# Tool implementation
def slugify(name: str) -> str:
    """Convert product name (possibly URL encoded) to WooCommerce-style slug."""
    name = unquote(name)  # ← decode "%20" thành khoảng trắng
    name = name.replace('&', '')
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("utf-8")
    name = name.lower()
    name = re.sub(r'[^a-z0-9]+', '-', name)
    name = name.strip('-')
    return name

@mcp.tool()
async def get_product_variations(product_slug: str) -> str:
    # Step 1: Get product by slug
    """
    Retrieves product variations using a product slug.

    The function first fetches the product details based on the provided slug.
    If the product is found, it fetches the product's variations using the
    product ID. It returns a formatted list of variations with attributes
    such as price, image, permalink, and stock status, along with the product
    description.

    Args:
        product_slug (str): The slug of the product for which to retrieve variations.

    Returns:
        str: A formatted string containing details of the product variations
             or an error message if the product or its variations cannot be fetched.
    """

    url = "https://museperfume.vn/wp-json/wc/v3/products"
    product_slug = slugify(product_slug)
    params = {"slug": product_slug, "per_page": 1}
    response = requests.get(url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET), params=params)

    if response.status_code != 200:
        return f"Failed to fetch product. Status {response.status_code}: {response.text}"

    data = response.json()
    if not data:
        return f"No product found with slug: '{product_slug}'"

    product = data[0]
    product_id = product["id"]
    product_name = product["name"]
    product_description = product.get("description")

    # Step 2: Get variations by product ID
    variations_url = f"https://museperfume.vn/wp-json/wc/v3/products/{product_id}/variations"
    variations_response = requests.get(variations_url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET))

    if variations_response.status_code != 200:
        return f"Failed to fetch variations. Status {variations_response.status_code}: {variations_response.text}"

    variations = variations_response.json()
    if not variations:
        return f"No variations found for product '{product_name}'"

    # Step 3: Format variations
    variation_list = []
    for var in variations:
        variation_list.append({
            "id": var.get("id"),
            "attributes": {a["name"]: a["option"] for a in var.get("attributes", [])},
            "price": var.get("price"),
            "image": var.get("image", {}).get("src"),
            "permalink": var.get("permalink"),
            "stock_status": var.get("stock_status"),
        })

    variation_list.append("description:" + product_description)
    return variation_list

@mcp.tool()
async def create_order_via_mcp(
    first_name: str,
    last_name: str,
    payment_method: str,
    payment_method_title: str,
    address: str,
    city: str,
    phone: str,
    email: str,
    product_id: int,
    quantity: int = 1
) -> str:
    """
    Tạo đơn hàng WooCommerce và trả về link thanh toán có mã QR MoMo.

    Args:
        first_name (str): Tên người mua
        last_name (str): Họ người mua
        address (str): Địa chỉ
        city (str): Thành phố
        phone (str): Số điện thoại
        email (str): Email
        product_id (int): ID sản phẩm (WooCommerce)
        quantity (int): Số lượng mua

    Returns:
        str: Thông tin đơn hàng hoặc lỗi.
    """

    url = "https://museperfume.vn/wp-json/wc/v3/orders"

    data = {
        "payment_method": payment_method,
        "payment_method_title": payment_method_title,
        "set_paid": False,
        "status": "pending",
        "billing": {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": address,
            "address_2": "",
            "city": city,
            "state": city,
            "postcode": "",
            "country": "VN",
            "email": email,
            "phone": phone
        },
        "shipping": {
            "first_name": first_name,
            "last_name": last_name,
            "address_1": address,
            "address_2": "",
            "city": city,
            "state": city,
            "postcode": "",
            "country": "VN"
        },
        "line_items": [
            {
                "product_id": product_id,
                "quantity": quantity
            }
        ]
    }

    response = requests.post(url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET), json=data)

    if response.status_code == 201:
        order = response.json()
        order_id = order["id"]
        order_key = order["order_key"]
        pay_url = f"https://museperfume.vn/checkout/order-received/{order_id}/?key={order_key}"
        return f"Đơn hàng đã được tạo thành công!\nMã đơn: {order_id}\n🔗 Link mã thanh toán:\n{pay_url}"
    else:
        return f"Lỗi khi tạo đơn hàng ({response.status_code}):\n{response.text}"


@mcp.tool()
def get_momo_qr_image_url(payment_page_url: str) -> str:
    """
    Truy cập vào link thanh toán WooCommerce và lấy URL hình ảnh mã QR MoMo.

    Args:
        payment_page_url (str): Đường dẫn thanh toán sau khi tạo đơn hàng.

    Returns:
        str: Đường dẫn hình ảnh mã QR hoặc thông báo lỗi.
    """
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        res = requests.get(payment_page_url, headers=headers)
        if res.status_code != 200:
            return f"Không truy cập được link thanh toán: {res.status_code}"

        soup = BeautifulSoup(res.text, 'html.parser')

        # Cách 1: Ưu tiên lấy ảnh nằm trong <div id="qrcode">
        qr_div = soup.find("div", id="qrcode")
        if qr_div:
            img_tag = qr_div.find("img")
            if img_tag and img_tag.get("src"):
                return img_tag["src"]

        # Cách 2: fallback – quét toàn bộ <img> nếu không tìm được trong qrcode
        img_tags = soup.find_all("img")
        for img in img_tags:
            src = img.get("src", "")
            if "/wp-json/bck/" in src or "momo" in src or "qr" in src:
                return src

        return "Không tìm thấy mã QR trên trang thanh toán."

    except Exception as e:
        return f"Lỗi khi truy cập trang thanh toán: {str(e)}"



# @mcp.tool()
# async def tavily_web_search(query: str) -> str:
#     """
#     Perform a web search.

#     Args:
#         query (str): The search query string.

#     Returns:
#         str: The search result from Tavily API. If the API key is not set, 
#         returns an error message prompting to set TAVILY_API_KEY.
#     """

#     api_key = os.getenv("TAVILY_API_KEY")

#     if not api_key:
#         return "Tavily API key not set. Please set TAVILY_API_KEY in your environment."
#     client = TavilyClient(api_key=api_key)

#     response = client.search(query, limit=2, search_depth="advanced", include_answer=True)

#     return response


@mcp.tool()
async def get_product_id_by_name_and_option(product_name: str, option: str) -> int:
    """
    Trả về ID của sản phẩm biến thể (variation) theo tên và option (ví dụ: dung tích).
    Dùng để hỗ trợ gọi tạo đơn hàng chính xác.

    Args:
        product_name (str): Tên sản phẩm chính (ví dụ: Chanel Bleu EDP)
        option (str): Tên option mong muốn (ví dụ: 100ml)

    Returns:
        int: ID của biến thể tương ứng hoặc -1 nếu không tìm thấy
    """
    variations = await get_product_variations(product_name)

    if isinstance(variations, str):
        # Trường hợp lỗi
        return -1

    for v in variations:
        if isinstance(v, dict):
            attrs = v.get("attributes", {})
            for attr_val in attrs.values():
                if attr_val.strip().lower() == option.strip().lower():
                    return v.get("id", -1)

    return -1  # Không tìm thấy

# Run the server
if __name__ == "__main__":
    mcp.run(transport='streamable-http')