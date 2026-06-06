import psycopg2
conn = psycopg2.connect('postgresql://postgres:admin@localhost:5432/recruitment_ai')
c = conn.cursor()
c.execute("UPDATE applications SET score_final = NULL, score_technique = NULL WHERE id = 92")
conn.commit()
print("Done - restored")
conn.close()