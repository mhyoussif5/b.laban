import os
import asyncio
import sqlite3

import cloudinary
import cloudinary.uploader

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field

# ==================== Cloudinary ====================

cloudinary.config(
    cloud_name="ywq1nmza",
    api_key="184542494378983",
    api_secret="AVtz_MXl8sThEkbO7qV1wo4OvVc",  # Click 'View API Keys' above to copy your API secret
    secure=True,
)


# ==================== Database ====================

DB_NAME = "b-laben-1.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database():
    with get_connection() as conn:

        # Products
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prodacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                img_url TEXT NOT NULL,
                name_ar TEXT NOT NULL,
                name_en TEXT NOT NULL,
                price REAL NOT NULL,
                descreption_ar TEXT NOT NULL,
                descreption_en TEXT NOT NULL,
                category TEXT NOT NULL
            )
        """)

        # Best seller
        conn.execute("""
            CREATE TABLE IF NOT EXISTS best_seller (
                id INTEGER PRIMARY KEY,
                best_seller_product_id INTEGER,
                FOREIGN KEY (best_seller_product_id)
                    REFERENCES prodacts(id)
                    ON DELETE SET NULL
            )
        """)

        # Orders
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exit_form (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                adress TEXT NOT NULL,
                stat TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Add created_at to an existing orders table if needed
        columns = conn.execute("PRAGMA table_info(exit_form)").fetchall()

        column_names = [column[1] for column in columns]

        if "created_at" not in column_names:
            conn.execute("""
                ALTER TABLE exit_form
                ADD COLUMN created_at TEXT
            """)

            conn.execute("""
                UPDATE exit_form
                SET created_at = CURRENT_TIMESTAMP
                WHERE created_at IS NULL
            """)


# ==================== Models ====================


class Product(BaseModel):
    img_url: str
    name_ar: str
    name_en: str
    price: float = Field(gt=0)
    descreption_ar: str
    descreption_en: str
    category: str


class BestSeller(BaseModel):
    prodact_id: int = Field(gt=0)


class Order(BaseModel):
    name: str
    phone: str
    adress: str
    stat: str


class OrderStatus(BaseModel):
    stat: str


# ==================== Automatic Order Deletion ====================


async def delete_old_orders():
    while True:
        try:
            with get_connection() as conn:
                conn.execute("""
                    DELETE FROM exit_form
                    WHERE created_at <= datetime('now', '-72 hours')
                """)

            print("Old orders checked successfully.")

        except Exception as error:
            print(f"Order cleanup error: {error}")

        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()

    cleanup_task = asyncio.create_task(delete_old_orders())

    try:
        yield
    finally:
        cleanup_task.cancel()

        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


# ==================== Upload Image ====================



@app.post("/upload-image")
def upload_image(image: UploadFile = File(...)):

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Please upload an image file."
        )

    try:
        result = cloudinary.uploader.upload(
            image.file,
            folder="b-laban"
        )

        return {
            "message": "Image uploaded successfully",
            "img_url": result["secure_url"]
        }

    except Exception as error:
        print("Cloudinary upload error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )

    finally:
        image.file.close()


# ==================== Get All Products ====================


@app.get("/prodacts")
def get_prodacts():
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        products = conn.execute("SELECT * FROM prodacts").fetchall()

        return [dict(product) for product in products]


# ==================== Add Product ====================


@app.post("/add-prodact")
def add_prodact(product: Product):

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO prodacts (
                img_url,
                name_ar,
                name_en,
                price,
                descreption_ar,
                descreption_en,
                category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                product.img_url,
                product.name_ar,
                product.name_en,
                product.price,
                product.descreption_ar,
                product.descreption_en,
                product.category,
            ),
        )

        product_id = cursor.lastrowid

    return {"message": "Product added successfully", "id": product_id}


# ==================== Update Product ====================


@app.put("/update-prodact/{prodact_id}")
def edit_prodact(prodact_id: int, product: Product):

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE prodacts
            SET img_url = ?,
                name_ar = ?,
                name_en = ?,
                price = ?,
                descreption_ar = ?,
                descreption_en = ?,
                category = ?
            WHERE id = ?
        """,
            (
                product.img_url,
                product.name_ar,
                product.name_en,
                product.price,
                product.descreption_ar,
                product.descreption_en,
                product.category,
                prodact_id,
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")

    return {"message": "Product updated successfully"}


# ==================== Delete Product ====================


@app.delete("/delete-prodact/{prodact_id}")
def delete_prodact(prodact_id: int):

    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM prodacts WHERE id = ?", (prodact_id,))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Product not found")

    return {"message": "Product deleted successfully"}


# ==================== Best Seller ====================


@app.get("/best-seller")
def get_best_seller():

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        product = conn.execute("""
            SELECT prodacts.*
            FROM prodacts
            JOIN best_seller
                ON prodacts.id = best_seller.best_seller_product_id
            LIMIT 1
        """).fetchone()

        if product is None:
            return {"message": "No best seller selected"}

        return dict(product)


# ==================== Set Best Seller ====================


@app.put("/best-seller")
def set_best_seller(data: BestSeller):

    with get_connection() as conn:

        product = conn.execute(
            "SELECT id FROM prodacts WHERE id = ?", (data.prodact_id,)
        ).fetchone()

        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

        conn.execute(
            """
            INSERT INTO best_seller (id, best_seller_product_id)
            VALUES (1, ?)
            ON CONFLICT(id)
            DO UPDATE SET best_seller_product_id = excluded.best_seller_product_id
        """,
            (data.prodact_id,),
        )

    return {"message": "Best seller updated successfully"}


# ==================== Random Products ====================


@app.get("/products/random")
def get_random_products():

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        products = conn.execute("""
            SELECT *
            FROM prodacts
            ORDER BY RANDOM()
            LIMIT 2
        """).fetchall()

        return [dict(product) for product in products]


# ==================== Add Order ====================


@app.post("/order-add")
def add_order(order: Order):

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO exit_form (
                name,
                phone,
                adress,
                stat
            )
            VALUES (?, ?, ?, ?)
        """,
            (order.name, order.phone, order.adress, order.stat),
        )

        order_id = cursor.lastrowid

    return {"message": "Order added successfully", "id": order_id}


# ==================== View Orders ====================


@app.get("/order-view")
def view_orders():

    with get_connection() as conn:
        conn.row_factory = sqlite3.Row

        orders = conn.execute("""
            SELECT *
            FROM exit_form
            ORDER BY id DESC
        """).fetchall()

        return [dict(order) for order in orders]


# ==================== Update Order Status ====================


@app.put("/update-order/{exit_form_id}")
def edit_order_status(exit_form_id: int, data: OrderStatus):

    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE exit_form
            SET stat = ?
            WHERE id = ?
        """,
            (data.stat, exit_form_id),
        )

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Order not found")

    return {"message": "Order status updated successfully"}
