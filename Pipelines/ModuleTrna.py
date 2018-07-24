"""
ModuleTrna.py - Tasks for running trna pipleine

"""

import os
import pysam
import CGATCore.Experiment as E
import CGATCore.IOTools as IOTools
import CGATCore.Pipeline as P
import CGATCore.Database as Database


def connectToUCSC(host="genome-mysql.cse.ucsc.edu",
                  user="genome",
                  database=None):
    """connect to UCSC database.

    Arguments
    ---------
    host : string
        Host to connect to
    user : string
        Username to connect with
    Database : string
        database to use

    Returns
    -------
    Database handle

    """
    dbhandle = Database.connect(url="mysql://{user}@{host}/{database}".format(**locals()))

    return dbhandle




def getRepeatDataFromUCSC(dbhandle,
                          repclasses,
                          outfile,
                          remove_contigs_regex=None,
                          job_memory="4G"):
    '''download data from UCSC database and write to `outfile` in
    :term:`gff` format.

    This method downloads repeats from the repeatmasker track at
    the UCSC.

    Arguments
    ---------
    dbhandle : object
       Database handle to UCSC mysql database
    repclasses : list
       List of repeat classes to select. If empty, all repeat classes
       will be collected.
    outfile : string
       Filename of output file in :term:`gff` format.
    remove_contigs_regex : string
       If given, remove repeats on contigs matching the regular
       expression given.

    '''
    cc = dbhandle.execute("SHOW TABLES LIKE '%%rmsk'")
    tables = [x[0] for x in cc.fetchall()]
    if len(tables) == 0:
        raise ValueError("could not find any `rmsk` tables")

    # now collect repeats
    tmpfile = P.get_temp_file(".")

    for table in tables:

        sql = """SELECT genoName, 'repeat', 'exon', genoStart+1, genoEnd,
        '.', strand, '.',
        CONCAT('class \\"', repClass, '\\"; family \\"',
        repFamily, '\\"; repName \\"', repName, '\\";')
        FROM %(table)s"""

        if repclasses:
            repclasses_str = ",".join(
                ["'" + x.strip() + "'" for x in repclasses])
            sql += ''' WHERE repClass in (%(repclasses_str)s) ''' % locals()

        sql = sql % locals()

        E.debug("executing sql statement: %s" % sql)
        cc = dbhandle.execute(sql)
        for data in cc.fetchall():
            tmpfile.write("\t".join(map(str, data)) + "\n")

    tmpfile.close()

    # sort gff and make sure that names are correct
    tmpfilename = tmpfile.name

    statement = ['''cat %(tmpfilename)s
    | sort -t$'\\t' -k1,1 -k4,4n
    | cgat gff2gff
    --method=sanitize
    --sanitize-method=genome
    --skip-missing
    --genome-file=%(genome_dir)s/%(genome)s
    --log=%(outfile)s.log ''']

    if remove_contigs_regex:
        statement.append('--contig-pattern="{}"'.format(
            ",".join(remove_contigs_regex)))

    statement.append('''| gzip > %(outfile)s ''')

    statement = " ".join(statement)

    P.run(statement, job_memory=job_memory)

    os.unlink(tmpfilename)


def process_trimmomatic(infile, outfile, phred, trimmomatic_options):
    """
    Runs the trimmomatic software
    """

    output_prefix = "processed.dir/" + infile.replace(".fastq.gz", "")
    job_threads = 2
    job_memory = "12G"

    statement = """
                trimmomatic SE -threads %(job_threads)s %(phred)s %(infile)s %(outfile)s
                %(trimmomatic_options)s 2>> %(output_prefix)s.log
                """ %locals()

    P.run(statement)
