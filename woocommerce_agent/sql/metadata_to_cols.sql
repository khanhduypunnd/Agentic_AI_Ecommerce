ALTER TABLE products
ADD COLUMN brand text,
ADD COLUMN name text,
ADD COLUMN option text,
ADD COLUMN price numeric(10,2),
ADD COLUMN description text,
ADD COLUMN stock_status text,
ADD COLUMN permalink text,
ADD COLUMN image text,
ADD COLUMN categories text;


UPDATE products
SET 
  brand = metadata->>'brand',
  name = metadata->>'name',
  option = metadata->>'option',
  price = (metadata->>'price')::numeric,
  description = metadata->>'description',
  stock_status = metadata->>'stock_status',
  permalink = metadata->>'permalink',
  image = metadata->>'image',
  categories = metadata->>'categories';



-- Index cho tìm kiếm theo brand
CREATE INDEX idx_products_brand ON products(brand);

-- Index cho tên sản phẩm (nếu hay search theo tên)
CREATE INDEX idx_products_name ON products(name);

-- Index cho tìm kiếm theo size
CREATE INDEX idx_products_option ON products(option);

-- Index cho tìm kiếm theo giá
CREATE INDEX idx_products_price ON products(price);

-- Index cho tìm kiếm theo tình trạng kho (còn hàng/hết hàng)
CREATE INDEX idx_products_stock ON products(stock_status);

-- Index cho tìm kiếm theo loại sản phẩm 
CREATE INDEX idx_products_categories ON products(categories);


