"""===========================
Pipeline gat
===========================

Overview
========

This pipeline performs gat enrichment over ChromHMM output and can be used to
annoate each of the chromatin states.
  
Usage
=====



Configuration
-------------

Default configuration files can be generated by executing:

   python <srcdir>/pipeline_gat.py config

Input files
-----------

None required except the pipeline configuration files.

Requirements
------------

Pipeline output
===============

Output is a heatmap of the annotateion states mapped to each chromHMM state.


Code
====

"""
import sys
import os
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib
from pylab import savefig
from ruffus import *
import ModuleGat
import cgatcore.pipeline as P
import cgatcore.experiment as E

# load options from the config file
PARAMS = P.get_parameters(
    ["%s/pipeline.yml" % os.path.splitext(__file__)[0],
     "../pipeline.yml",
     "pipeline.yml"])


SEQUENCESUFFIXES = ("*.bed.gz")

BEDTARGET = tuple([os.path.join(".", suffix_name)
                       for suffix_name in SEQUENCESUFFIXES])


@follows(mkdir("bed_segments.dir"))
@split(PARAMS['chromhmm_segment_bed'],
           "bed_segments.dir/*.bed")
def segment_bed(infile, outfiles):
    """Will segment the output chromHMM bed file 
    into seperate segmented bed files so that gat can be ran"""

    df = pd.read_table("JMJD3_J4_10_segments.bed", header=None)
    for index, table in df.groupby(3):
        name = "bed_segments.dir/" + index + "_segments.bed"
        table.to_csv(name, index=False, sep="\t", header=False)

@transform(segment_bed,
           suffix(".bed"),
           ".out")
def run_gat(infile, outfile):
    '''run GAT over the split segments for the bed files.'''

    bed_name = infile.replace("bed_segments.dir/", "")
    bed_name = bed_name.replace("_segments.bed", "")
    contig = PARAMS["gat_contig"]
    annotations = PARAMS['gat_annotation_bed']

    statement = '''gat-run.py --segments=%(infile)s --annotations=%(annotations)s --workspace=%(contig)s --log=%(contig)sgta.log > %(outfile)s'''

    P.run(statement, job_condaenv="gat")


@merge(run_gat, "bed_segments.dir/merged_gat.csv")
def merge_gat(infiles, outfile):
    """This function collects the log2 fold change values from gat and then merges them into a single csv file"""

    
    data_frame = pd.DataFrame()

    for infile in infiles:
        df = pd.read_table(infile)
        basename = os.path.basename(infile)
        name = basename.replace("_segments.out", "")
        annotation = df['annotation']
        data = df['l2fold']
        data = data.rename(name)
        data_frame = data_frame.append(data)
    data_frame = data_frame.append(annotation)
    data_frame = data_frame.transpose()
    data_frame = data_frame.set_index(annotation)
    del data_frame['annotation']
    data_frame.to_csv(outfile)

@transform(merge_gat,
           suffix(".csv"),
           "\1.final")
def plot_heat(infile, outfile):
    """Generates a heatmap of the merged data from gat"""

    comb = pd.read_csv(infile)
    comb.set_index("annotation", inplace=True)
    df = comb.transpose()

    fig = sns.heatmap(df, annot=False, fmt="g", cmap='BuGn_r', square=True)
    figure = fig.get_figure()    
    figure.savefig(outfile, dpi=400)
    


#############################################################
# Annotation of regulated genes
############################################################

@originate("transcript2gene.tsv")
def transcript2gene(outfile):
    """generate a transcript2 gene map for processing tts and tss """

    infile = PARAMS['geneexpression_coding_gene_gtf']
    statement = "zcat %(infile)s | cgat gtf2tsv --output-map=transcript2gene > transcript2gene.tsv"

    P.run(statement)

@follows(mkdir("genexpression.dir"))
@active_if(PARAMS['geneexpression_present'])
@transform(PARAMS['geneexpression_gene_lists'],
           regex(".*/(\S+).csv"),
           r"genexpression.dir/coding_\1.bed.gz")
def coding_gene_parse(infile, outfile):
    """Filter a gtf using gene lists and then outut them as gtf"""

    bedfile = PARAMS['geneexpression_coding_gene']

    statement = """zcat %(bedfile)s | grep -f %(infile)s | gzip > %(outfile)s"""

    P.run(statement)

@transform(PARAMS['geneexpression_gene_lists'],
           regex(".*/(\S+).csv"),
           add_inputs(transcript2gene),
           r"genexpression.dir/transcripts_\1.txt")
def gene2trans_output(infiles, outfile):
    """Filter a gtf using gene lists and then outut them as gtf"""

    infile, transmap = infiles

    ModuleGat.gene2trans(infile, outfile, transmap)

    # Not needed now as I can use coding gene tts and tss instead


@active_if(PARAMS['geneexpression_present'])
@transform(PARAMS['geneexpression_gene_lists'],
           regex(".*/(\S+).csv"),
           r"genexpression.dir/tts_\1.bed.gz")
def tts_gene_parse(infile, outfile):
    """Filter a gtf using gene lists and then outut them as gtf"""

    bedfile = PARAMS['geneexpression_tts']

    tmpfile = P.get_temp_filename()

    statement = """zcat %(bedfile)s | grep -f %(infile)s > %(tmpfile)s &&
                   cat %(tmpfile)s | awk '{$4 = "TTS"; print}' OFS='\\t' | gzip > %(outfile)s"""

    P.run(statement)


@active_if(PARAMS['geneexpression_present'])
@transform(PARAMS['geneexpression_gene_lists'],
           regex(".*/(\S+).csv"),
           r"genexpression.dir/tss_\1.bed.gz")
def tss_gene_parse(infile, outfile):
    """Filter a gtf using gene lists and then outut them as gtf"""

    bedfile = PARAMS['geneexpression_tss']

    tmpfile = P.get_temp_filename()

    statement = """zcat %(bedfile)s | grep -f %(infile)s > %(tmpfile)s &&
                   cat %(tmpfile)s | awk '{$4 = "TSS"; print}' OFS='\\t' | gzip > %(outfile)s"""

    P.run(statement)

@transform(coding_gene_parse,
           regex("genexpression.dir/(\S+).bed.gz"),
           r"genexpression.dir/extended_\1.bed.gz")
def extend_coding(infile, outfile):
    """extend the bed file =/-2000bp"""

    ModuleGat.extend_bed(infile, outfile)

@collate((extend_coding, tss_gene_parse, tts_gene_parse),
         regex("genexpression.dir/(\S+)_([a-z]+regulated).bed.gz"),
         r"genexpression.dir/\2_merged.bed.gz")
def merge_bedfiles(infiles, outfile):
    """Merge the bed files togather"""

    files = " ".join(infiles)
    statement = "cat %(files)s  > %(outfile)s"

    P.run(statement)

@follows(mkdir("bed_segments_up_down.dir"))
@subdivide(segment_bed,
           regex("bed_segments.dir/(\S+).bed"),
           add_inputs(merge_bedfiles),
           [r"bed_segments_up_down.dir/downregulated_\1.out", 
            r"bed_segments_up_down.dir/upregulated_\1.out"])
def run_gat_merged(infiles, outfiles):
    """run gat on merged bedfile """

    segments, downreg, upreg = infiles
    contigs = PARAMS['gat_contig']

    downout, upout = outfiles
    statement = """gat-run.py 
                   --segments=%(segments)s
                   --annotations=%(downreg)s 
                   --workspace=%(contigs)s
                   --log=downregulated_gta.log > %(downout)s """

    P.run(statement)

    statement = """gat-run.py 
                   --segments=%(segments)s 
                   --annotations=%(upreg)s 
                   --workspace=%(contigs)s
                   --log=gta.log > %(upout)s """

    P.run(statement)

@collate(run_gat_merged,
         regex("bed_segments_up_down.dir/(\S+)_\S+_\S+.out"),
         r"bed_segments_up_down.dir/\1_merged_gat.csv")
def merge_gat_regulated(infiles, outfile):
    """This function collects the log2 fold change values from gat and then merges them into a single csv file"""

    
    data_frame = pd.DataFrame()

    for infile in infiles:
        df = pd.read_table(infile)
        basename = os.path.basename(infile)
        name = basename.replace("_segments.out", "")
        annotation = df['annotation']
        data = df['l2fold']
        data = data.rename(name)
        data_frame = data_frame.append(data)
    data_frame = data_frame.append(annotation)
    data_frame = data_frame.transpose()
    data_frame = data_frame.set_index(annotation)
    del data_frame['annotation']
    data_frame.to_csv(outfile)

@transform(merge_gat_regulated,
           suffix(".csv"),
           r"\1.eps")
def plot_heat_regulated(infile, outfile):
    """Generates a heatmap of the merged data from gat"""

    comb = pd.read_csv(infile)
    comb.set_index("annotation", inplace=True)
    df = comb.transpose()

    fig = sns.heatmap(df, annot=False, fmt="g", cmap='Reds', square=True)
    figure = fig.get_figure()    
    figure.savefig(outfile, dpi=400)


##########################################
# For each segment find top 10 enrichments
##########################################

# Annotate peaks using homer
@transform(segment_bed,
           suffix(".bed"),
           ".txt")
def run_homer(infile, outfile):
    "Run homer to define annotations"

    genome = PARAMS['homer_genome']
    statement = """annotatePeaks.pl %(infile)s %(genome)s > %(outfile)s"""

    P.run(statement)

@follows(merge_gat, coding_gene_parse, tss_gene_parse, tts_gene_parse) 
def full():
    pass

def main(argv=None):
    if argv is None:
        argv = sys.argv
    P.main(argv)


if __name__ == "__main__":
    sys.exit(P.main(sys.argv))    
