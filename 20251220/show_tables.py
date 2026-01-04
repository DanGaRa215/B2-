import psycopg2

def show_tables(db_name='tabelog_db', user='dangararara'):
    try:
        conn = psycopg2.connect(host="localhost", database=db_name, user=user)
        cur = conn.cursor()
        
        # Get list of tables
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cur.fetchall()
        
        for table in tables:
            table_name = table[0]
            print(f"\nTable: {table_name}")
            print("-" * 50)
            print(f"  {'Column Name':<20} {'Data Type':<20} {'Nullable'}")
            print("-" * 50)
            
            # Get columns for each table
            cur.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position;
            """)
            columns = cur.fetchall()
            for col in columns:
                print(f"  {col[0]:<20} {col[1]:<20} {col[2]}")
                
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn: conn.close()

if __name__ == "__main__":
    show_tables()
