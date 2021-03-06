"""===========================
Pipeline downsample fastq
===========================

.. Replace the documentation below with your own description of the
   pipeline's purpose

Overview
========

This pipeline computes the word frequencies in the configuration
files :file:``pipeline.yml` and :file:`conf.py`.

Usage
=====

See :ref:`PipelineSettingUp` and :ref:`PipelineRunning` on general
information how to use CGAT pipelines.

Configuration
-------------

The pipeline requires a configured :file:`pipeline.yml` file.
CGATReport report requires a :file:`conf.py` and optionally a
:file:`cgatreport.ini` file (see :ref:`PipelineReporting`).

Default configuration files can be generated by executing:

   python <srcdir>/pipeline_cat_fastq.py config

Input files
-----------

None required except the pipeline configuration files.

Requirements
------------

The pipeline requires the results from
:doc:`pipeline_genesets`. Set the configuration variable
:py:data:`annotations_database` and :py:data:`annotations_dir`.

On top of the default CGAT setup, the pipeline requires the following
software to be in the path:

.. Add any additional external requirements such as 3rd party software
   or R modules below:

Requirements:

* samtools >= 1.1

Pipeline output
===============

.. Describe output files of the pipeline here

Glossary
========

.. glossary::


Code
====

"""
import sys
import os
from ruffus import *
import cgatcore.pipeline as P
import cgatcore.experiment as E

# load options from the config file
PARAMS = P.get_parameters(
    ["%s/pipeline.yml" % os.path.splitext(__file__)[0],
     "../pipeline.yml",
     "pipeline.yml"])


SEQUENCESUFFIXES = ("*.fastq.1.gz",
                    "*.fastq.2.gz",
                    "*.fastq.gz"
                    )

@transform("*.fastq.*.gz",
         regex("(\S+).fastq.(\S).gz"),
         r"downsample-\1.fastq.\2.gz")
def downsample(infile, outfile):
    '''downsample fastq files using seqtk tool.'''

    tmp_file = P.get_temp_filename(".")
    statement = '''zcat %(infile)s > %(tmp_file)s && seqtk sample -2 -s100 %(tmp_file)s %(downsample_read)s | gzip > %(outfile)s'''

    job_memory= "30G"
    P.run(statement)
    os.unlink(tmp_file)


@follows(downsample)
def full():
    pass

def main(argv=None):
    if argv is None:
        argv = sys.argv
    P.main(argv)


if __name__ == "__main__":
    sys.exit(P.main(sys.argv))    
