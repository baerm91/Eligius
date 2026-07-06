
# try to load native mysqlclient and fallback to pure python
try:
    import mysqlclient

except ImportError:
    import pymysql

    pymysql.install_as_MySQLdb()
