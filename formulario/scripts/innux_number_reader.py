"""Consulta exacta y de solo lectura. Entrada por stdin; nunca registra DNI o fechas."""
import datetime,json,re,sys

CONNECTION=r'DRIVER={SQL Server};SERVER=.\TOPFITNESS;DATABASE=InnuxSports;Trusted_Connection=yes;APP=TopFitnessAltasSoloLectura;'
QUERY="""SELECT TOP 2 IDCliente,Numero FROM dbo.Clientes
WHERE UPPER(REPLACE(REPLACE(LTRIM(RTRIM(NIF)), ' ', ''), '-', ''))=?
AND CONVERT(date,DataNascimento)=? ORDER BY IDCliente"""

def lookup(request,connect):
    document=request.get('document','')
    birth=request.get('birth_date','')
    if not isinstance(document,str) or not isinstance(birth,str):return {'status':'INVALID_INPUT'}
    document=document.replace(' ','').replace('-','').upper()
    if not re.fullmatch('[A-Z0-9]{3,35}',document):return {'status':'INVALID_INPUT'}
    try:date=datetime.date.fromisoformat(birth)
    except (ValueError,TypeError):return {'status':'INVALID_INPUT'}
    connection=connect(CONNECTION,timeout=5,autocommit=True)
    try:
        connection.timeout=6;cursor=connection.cursor()
        try:rows=cursor.execute(QUERY,document,date).fetchall()
        finally:cursor.close()
        if not rows:return {'status':'NOT_FOUND'}
        if len(rows)!=1:return {'status':'AMBIGUOUS'}
        client_id,number=rows[0]
        if type(client_id) is not int or client_id<=0 or type(number) is not int or number<=0:return {'status':'NUMBER_PENDING'}
        cursor=connection.cursor()
        try:owners=cursor.execute('SELECT TOP 2 IDCliente FROM dbo.Clientes WHERE Numero=? ORDER BY IDCliente',number).fetchall()
        finally:cursor.close()
        if len(owners)!=1 or owners[0][0]!=client_id:return {'status':'AMBIGUOUS'}
        return {'status':'FOUND','client_id':str(client_id),'number':str(number)}
    finally:connection.close()

def main():
    try:
        raw=sys.stdin.buffer.read(4097)
        if len(raw)>4096:raise ValueError()
        request=json.loads(raw)
        if not isinstance(request,dict):raise ValueError()
        import pyodbc
        result=lookup(request,pyodbc.connect)
    except Exception:result={'status':'UNAVAILABLE'}
    print(json.dumps(result))

if __name__=='__main__':main()
