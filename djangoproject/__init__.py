# Try native mysqlclient (C-Extension) and fall back to pure-Python pymysql
try:
    import MySQLdb
except ImportError:
    import pymysql

    pymysql.install_as_MySQLdb()
