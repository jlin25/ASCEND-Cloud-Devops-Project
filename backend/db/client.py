#Establish a connection to database. Import in files that need to interact with the database
#For example, in a file under backend folder, import with "from db.client import database"
import os
from dotenv import load_dotenv
from supabase import create_client
import pathlib

load_dotenv()
database = create_client(os.getenv("DB_URL"), os.getenv("DB_SERVICE_KEY"))