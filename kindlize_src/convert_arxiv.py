#Last-modified: 28 Oct 2013 06:28:17 PM
import os
from urlparse import urlsplit
from tempfile import mkstemp
from glob import glob
import urllib2
import tarfile
import shutil
import re



# syle regexp taken directly from arxiv2bib
NEW_STYLE = re.compile(r'\d{4}\.\d{4}(v\d+)?$')
NEW_STYLE2 = re.compile(r'\d{4}\.\d{5}(v\d+)?$')
OLD_STYLE = re.compile( r'(astro-ph)' + r'(\.[A-Z]{2})?/\d{7}(v\d+)?$' )

# geometry configuration
geostr     = "\usepackage[paperwidth=13.8cm, paperheight=22.0cm, top=0.5cm, left=1.0cm, right=0.5cm, bottom=0.5cm]{geometry}\n"
geostr_apj = "\usepackage[paperwidth=13.8cm, paperheight=22.0cm, top=2.3cm, left=1.5cm, right=0.0cm, bottom=-1.0cm]{geometry}\n"
geostr_mn  = "\usepackage[paperwidth=13.8cm, paperheight=22.0cm, top=2.5cm, left=0.5cm, right=0.5cm, bottom=0.5cm]{geometry}\n"
geostr_els = "\usepackage[paperwidth=15.8cm, paperheight=22.0cm, top=0.5cm, left=0.5cm, right=0.5cm, bottom=0.3cm]{geometry}\n"
geostr_aas = "\usepackage[paperwidth=13.8cm, paperheight=22.0cm, top=3.5cm, left=1.5cm, right=0.2cm, bottom=2.5cm]{geometry}\n"


# latex cls library
jname = { "elsart_mm" : "Elsevier Science",
          "aa"        : "AA",
          "emulateapj": "ApJ",
          "aastex"    : "AAS Preprint",
          "aastex6"    : "AAS Preprint 6",
          "mn2e"      : "MNRAS",
          "article"   : "Generic Article",
          "elsarticle": "Elsevier Science",
          "revtex4"   : "Physics Review",
        }

#banned_packages = ["hyperref", "emulateapj5"]
banned_packages = ["emulateapj5"]

old_files = ["aaspp4.sty", "psfig.sty", "flushrt.sty", "mn.cls"]

class KindleException(Exception):
    pass

def url2name(url):
    return(os.path.basename(urlsplit(url)[2]))

def download(url, saveDir):
    localName = url2name(url)
    req = urllib2.Request(url)
    r = urllib2.urlopen(req)
    if r.info().has_key('Content-Disposition'):
        # If the response has Content-Disposition, we take file name from it
        localName = r.info()['Content-Disposition'].split('filename=')[1]
        if localName[0] == '"' or localName[0] == "'":
            localName = localName[1:-1]
    elif r.url != url:
        # if we were redirected, the real file name we take from the final URL
        localName = url2name(r.url)
    # get it to a default directory
    if saveDir is not None:
        absFileName = os.path.join(saveDir, localName)
    else:
        absFileName = localName
    print("as %s" % absFileName)
    f = open(absFileName, 'wb')
    f.write(r.read())
    f.close()
    return(absFileName)

def findFigs(t, ext="ps"):
    """ find all the figure files with specified extensions. """
    figfiles = []
    for file in t.getnames() :
        if file.endswith("."+ext) :
            print("found %s image in the tar bundle %s" % (ext, file))
            figfiles.append(file)
    return(figfiles)

def force_mkdir(desdir):
    """ clear out the desdir you want and remake the directory available.
    """
    if os.path.exists(desdir):
        shutil.rmtree(desdir)
    else :
        try :
            os.mkdir(desdir)
        except OSError, err :
            raise KindleException("mkdir %s failed, %s"%(desdir, err))

def examine_texenv(desdir):
    """ find tex file, cls file, bst file, and bbl file in the tar ball.
    """
    texfiles = []
    clsfiles = []
    bstfiles = []
    bblfiles = []
    for file in os.listdir(desdir) :
        if file.endswith(".tex") :
            print("found tex file in the tar bundle %s" % file)
            texfiles.append(file)
        elif file.endswith(".cls") :
            print("found cls file in the tar bundle %s" % file)
            clsfiles.append(file)
        elif file.endswith(".bst") :
            print("found bst file in the tar bundle %s" % file)
            bstfiles.append(file)
        elif file.endswith(".bbl") :
            print("found bbl file in the tar bundle %s" % file)
            bblfiles.append(file)
    return(texfiles, clsfiles, bstfiles, bblfiles)

def getMaster(texfiles, desdir):
    """ copy master tex file to main.tex and determine whether latex2e or latex2.09 is needed.
    """
    masterfile = None
    for texfile in texfiles :
        texfile = os.path.join(desdir, texfile)
        content = open(texfile).read()
        if 'documentclass' in content:
            # make sure master file is main.tex
            print("copying main tex file")
            masterfile = os.path.join(desdir, "main.tex")
            shutil.move(texfile, masterfile)
            texversion = "latex2e"
        elif r'\begin{document}' in content:
            # make sure master file is main.tex
            print("copying main tex file, possibly latex2.09 file")
            masterfile = os.path.join(desdir, "main.tex")
            shutil.move(texfile, masterfile)
            texversion = "latex2.09"
    if masterfile is None :
        raise KindleException("missing master tex file or stone-age tex version?")
    return(masterfile, texversion)

def getBiblio(bblfiles, desdir):
    """ copy bbl if there is one and only one such file """
    if len(bblfiles) == 1 :
        # assume everyone is either using bbl or put citations in main tex.
        # no bib file
        bblname = bblfiles[0]
        # make sure this works
        bblfile_old = os.path.join(desdir, bblfiles[0])
        bblfile_new = os.path.join(desdir, "bibmain.bbl")
        print("copying main bbl file from %s"% bblfiles[0])
        # print bblfile_old
        # print bblfile_new
        shutil.copy(bblfile_old, bblfile_new)
    else:
        print("multiple bbl files, confused, do nothing")
        bblname = None
    return(bblname)

def checkMaster(masterfile, texversion) :
    """ find document class and first author name
    """
    if texversion == "latex2.09" :
        classname   = "old"
        classoption = "old"
        f = open(masterfile, "r")
        q = re.compile("[^\%]author[\[|\]|\w|\s|\.|\~]*\{([\w|\s|\.|\~]+)")
        for line in f.readlines():
            qresult = q.match(line)
            if qresult :
                firstauthor = qresult.group(1)
                break
        if qresult :
            try :
                author = firstauthor.split()[-1]
            except IndexError :
                author = "unknown"
        else :
            author = "unknown"
        f.close()
        return(classoption, classname, author)
    classname   = None
    classoption = None
    firstauthor = None
    f = open(masterfile, "r")
    # now the classname could be any non-space character.
    p = re.compile("[^\%]documentclass(.*)\{(\S+)\}")
    q = re.compile("[^\%]author\{([\w|\s|\.|\~]+)")
    # this need to be constantly improved.
    q_mn  = re.compile("[^\%]author\[([\w|\s|\.|\~|\\\\|\&]*)\]")
    q_els = re.compile("[^\%]author\[[\d|\,]*\]\{([\w|\s|\.|\~]+)\}")
    for line in f.readlines():
        presult = p.match(line)
        if presult :
            classoption = presult.group(1)
            classname   = presult.group(2)
        if classname is None :
            qresult = None
        elif classname == "mn2e" :
            qresult = q_mn.match(line)
        elif classname == "elsarticle" :
            qresult = q_els.match(line)
        else :
            qresult = q.match(line)
        #
        if qresult :
            firstauthor = qresult.group(1)
            break
    f.close()
    if classname :
        print("documentclass is %s"% classname)
    else :
        raise KindleException("missing classname?")
    if classoption :
        print("documentclass option is %s"% classoption)
    else :
        raise KindleException("missing classoption?")
    if firstauthor :
        firstauthor = firstauthor.replace("~", " ")
        firstauthor = firstauthor.replace(". ", "_")
        try :
            if classname == "mn2e" :
                author = firstauthor.split()[0]
            else :
                author = firstauthor.split()[-1]
        except IndexError:
            author = "unknown"
    else :
        author = "unknown"
    print("author: %s"%author)
    return(classoption, classname, author)

def getClass(classname, clibDir, clsfiles, bstfiles, desdir):
    """ copy corresponding style files based on classname.
    """
    if classname == "article" or classname == "old" :
        # safe
        return(None)
    clsfile = ".".join([classname, "cls"])
    if not (clsfile in clsfiles) :
        print("%s needed"%clsfile)
        if file_exists(os.path.join(clibDir, clsfile)):
            shutil.copy(os.path.join(clibDir, clsfile), desdir)
        else :
            raise KindleException("failed to find it in the cls library")
    # extra files
    if classname == "revtex4" or classname == "emulateapj" or classname == "revtex4-1" :
        shutil.copy(os.path.join(clibDir, "revsymb.sty"), desdir)
        shutil.copy(os.path.join(clibDir, "aps.rtx.tex"), desdir)
        shutil.copy(os.path.join(clibDir, "10pt.rtx.tex"), desdir)
        shutil.copy(os.path.join(clibDir, "revtex4.cls"), desdir)
        shutil.copy(os.path.join(clibDir, "revtex4-1.cls"), desdir)
        shutil.copy(os.path.join(clibDir, "epsf.sty"), desdir)
        shutil.copy(os.path.join(clibDir, "apjfonts.sty"), desdir)
        shutil.copy(os.path.join(clibDir, "rmp.rtx"), desdir)
    if classname == "elsarticle" :
        shutil.copy(os.path.join(clibDir, "epsf.tex"), desdir)
    bstfile = ".".join([classname, "bst"])
    if classname == "emulateapj" :
        # just copy the apj.bst file
        shutil.copy(os.path.join(clibDir, "apj.bst"), desdir)
    else :
        if not (bstfile in bstfiles) :
            if file_exists(os.path.join(clibDir, bstfile)):
                shutil.copy(os.path.join(clibDir, bstfile), desdir)
            else :
                print("probably the references will be messed up")

def getOpt(classoption):
    """ determine documentclass options for updating geometry and column info.
    """
    if classoption == "[]" or classoption == "[ ]":
        # human stupidity is ubiquitous.
        classopts = []
        hasoptbracket = True
    elif classoption != "old" and classoption is not None :
        classopts = classoption.lstrip("[").rstrip("]").split(",")
        if len(classopts) == 1 and classopts[0] == "" :
            print("empty class options")
            hasoptbracket = False
        else :
            print(classopts)
            hasoptbracket = True
    else :
        classopts = []
        hasoptbracket = False
        print("no class options")
    return(hasoptbracket, classopts)

def handleOldTeX(texversion, clibDir, desdir) :
    """ copy all the old style files so that the old TeX file can be compiled.
    """
    if texversion == "latex2.09" :
        for file in old_files :
            fold = os.path.join(clibDir, file)
            shutil.copy(fold, desdir)

def dropit(inpdf, dropDir, where="") :
    pdf = os.path.basename(inpdf)
    despdf = os.path.join(dropDir, where, pdf)
    if file_exists(despdf):
        base = despdf.rstrip(".pdf")
        fsimi = glob(base+"*"+".pdf")
        for i in xrange(10):
            newpdf = base + "-" + str(i) + ".pdf"
            if newpdf in fsimi :
                continue
            else :
                shutil.copy(inpdf, newpdf)
                print("drop %s into dropbox  as %s"%(pdf, newpdf))
                break
    else :
        shutil.copy(inpdf, despdf)
        print("drop %s into dropbox  as %s"%(pdf, despdf))

def do_latex(clibDir, desdir, masterfile, use_pdflatex=False) :
    if False:
        # makefile deprecated
        if use_pdflatex :
            mkfile = os.path.join(clibDir, "Makefile_pdflatex")
        else :
            mkfile = os.path.join(clibDir, "Makefile_latex")
        shutil.copy(mkfile, os.path.join(desdir, "Makefile"))
        latexmk = "make"
    else:
        print ("using latexmk instead")
        if use_pdflatex :
            latexmk = "latexmk -pdf"
        else:
            latexmk = "latexmk"
    cwd = os.getcwd() # get current directory
    os.chdir(desdir)
    try:
        os.system(latexmk)
    finally:
        os.chdir(cwd)
    pdfout = os.path.join(desdir, masterfile.replace(".tex", ".pdf"))
    if file_exists(pdfout):
        print("sucessfully generated kindle pdf")
        return(pdfout)
    else :
        print("failed to generate kindle pdf")
        return(None)

def file_exists(file):
    try:
        f = open(file, "r")
        f.close()
        return(True)
    except :
        return(False)

def parse_documentclass(classname, classopts, desdir):
    if classname == "old" :
        return("default", None, None)
    col_set = "default"
    onecol_arg = "onecolumn"
    twocol_arg = "twocolumn"
    if (classname == "elsart_mm"  or classname == "aa"      or
        classname == "emulateapj" or classname == "aastex"  or
        classname == "aastex6"  or
        classname == "elsarticle" or classname == "revtex4" or
        classname == "mn2e"       or classname == "article") :
        print("Journal Name: %20s"%jname[classname])
        print("`one/twocolumn` option is available")
        if onecol_arg in classopts :
            col_set = "one"
        elif twocol_arg in classopts :
            col_set = "two"
    else :
        print("unknown documentclass, searching the current directory...")
        _clsfile = os.path.join(desdir, classname + ".cls")
        if file_exists(_clsfile) :
            print("%s found, continue to next step" % _clsfile)
            # if onecol_arg can be found in the local clsfile, repeat above
            if findstr(_clsfile, onecol_arg) :
                if onecol_arg in classopts :
                    col_set = "one"
                elif twocol_arg in classopts :
                    col_set = "two"
            else :
                return("default", None, None)
        else :
            print("%s not found" % _clsfile)
            raise RuntimeError("unknown documentclass, please update library")

    if col_set == "one":
        print("`onecolumn` enabled")
    elif col_set == "two":
        print("`twocolumn` enabled")
    else :
        print("the existing file uses default column settting")
    return(col_set, onecol_arg, twocol_arg)

def substituteAll(file, pattern, subst):
    #Create temp file
    fh, abs_path = mkstemp()
    new_file = open(abs_path,'w')
    old_file = open(file)
    for line in old_file:
        if re.search(pattern, line):
            print("find pattern in %s"%line)
            new_file.write(re.sub(pattern, subst, line))
        else :
            new_file.write(line)
    #close temp file
    new_file.close()
    os.close(fh)
    old_file.close()
    #Remove original file
    os.remove(file)
    #Move new file
    shutil.move(abs_path, file)

def findstr(file, str) :
    f = open(file, 'r')
    lines = f.read()
    answer = lines.find(str)
    return(answer)

def replaceAll(file, pattern, subst):
    #Create temp file
    fh, abs_path = mkstemp()
    new_file = open(abs_path,'w')
    old_file = open(file)
    for line in old_file:
        new_file.write(line.replace(pattern, subst))
    #close temp file
    new_file.close()
    os.close(fh)
    old_file.close()
    #Remove original file
    os.remove(file)
    #Move new file
    shutil.move(abs_path, file)

def commentALL(file, pattern):
    #Create temp file
    fh, abs_path = mkstemp()
    new_file = open(abs_path,'w')
    old_file = open(file)
    for line in old_file:
        if pattern.match(line):
            new_file.write(r"%" + line)
        else :
            new_file.write(line)
    #close temp file
    new_file.close()
    os.close(fh)
    old_file.close()
    #Remove original file
    os.remove(file)
    #Move new file
    shutil.move(abs_path, file)

def getTar(arxivid, saveDir):
    chkres = is_new(arxivid)
    if chkres is True :
        url  = "".join(["http://arxiv.org/e-print/", arxivid])
        year = arxivid[0:2]
    elif chkres is False :
        num = arxivid.split("/")[-1]
        year = num[0:2]
        url = "".join(["http://arxiv.org/e-print/astro-ph/", num])
    else :
        raise RuntimeError("invalid id, please check your input")
    print("downloading source from %s" % url)
    fname = download(url, saveDir)
    return(fname, year)

def is_new(id):
    """
    Checks if id is a new arxiv identifier
    http://arxiv.org/help/arxiv_identifier_for_services
    """
    if NEW_STYLE.match(id) is not None :
        return(True)
    elif NEW_STYLE2.match(id) is not None:
        return(True)
    elif OLD_STYLE.match(id) is not None:
        return(False)
    else :
        return(None)

def convert(filename, year, saveDir, clibDir, dropDir, font, fontheight, fontwidth):
    """ the main procedure.
    """
    # font name
    fontstr = "".join(["\usepackage{", font, "}\n"])
    # enbiggen font
    magnifystr = "".join(["\n", r"\\fontsize{", fontheight, "}{", fontwidth, "}\selectfont","\n"])
    try :
        print('%20s  is a tar file? %s \n continue' % (filename, tarfile.is_tarfile(filename)))
    except IOError, err :
        print('%20s  is a tar file? %s \n exiting' % (filename, err))
        return(None)
    # desdir: intermediate directory to store files and recompile, should be
    # non-existent otherwise will be wiped out by the code
    desdir = os.path.join(saveDir, "outdir")
    force_mkdir(desdir)
    # open the tar file
    t = tarfile.open(filename, 'r')
    pdffiles = findFigs(t, "pdf")
    pngfiles = findFigs(t, "png")
    # decide if pdflatex is needed based on whether pdf/png files are used.
    if len(pdffiles) > 0 or len(pngfiles) > 0 :
        use_pdflatex = True
    else :
        use_pdflatex = False
    # extract content
    t.extractall(desdir)
    # go = raw_input('go to next step?') # debug
    texfiles, clsfiles, bstfiles, bblfiles = examine_texenv(desdir)
    # go through all files
    # go = raw_input('go to next step?') # debug
    masterfile, texversion = getMaster(texfiles, desdir)
    # deal with old latex2.09 files
    # go = raw_input('go to next step?') # debug
    handleOldTeX(texversion, clibDir, desdir)
    # copy bbl files if there is one
    bblname = getBiblio(bblfiles, desdir)
    # bblname = None
    # examine documentclass and find author
    # go = raw_input('go to next step?') # debug
    classoption, classname, author = checkMaster(masterfile, texversion)
    # copy style files
    # go = raw_input('go to next step?') # debug
    getClass(classname, clibDir, clsfiles, bstfiles, desdir)
    # find options of documentclass
    # go = raw_input('go to next step?') # debug
    hasoptbracket, classopts = getOpt(classoption)
    # parse documentclass and options
    # go = raw_input('go to next step?') # debug
    col_set, onecol_arg, twocol_arg = parse_documentclass(classname, classopts, desdir)
    # heavy duty modification of the master TeX file
    # go = raw_input('go to next step?') # debug
    kindlizeit(masterfile, hasoptbracket, classname, col_set, onecol_arg,
               twocol_arg, fontstr, magnifystr, bblname)
    # recompile
    # go = raw_input('go to next step?') # debug
    pdfout = do_latex(clibDir, desdir, masterfile, use_pdflatex=use_pdflatex)
    #
    # rename
    newpdfname = author + year + ".pdf"
    newpdf = os.path.join(desdir, newpdfname)
    shutil.move(pdfout, newpdf)
    print("generated pdf file: %s " % newpdf)
    return(newpdf)

def kindlizeit(masterfile, hasoptbracket, classname, col_set, onecol_arg,
               twocol_arg, fontstr, magnifystr, bblname):
    """ diagonose the master TeX file.
    """
    # make onecolumn pdf
    if col_set == "one" :
        pass
    elif col_set == "two" :
        if onecol_arg is not None :
            replaceAll(masterfile, twocol_arg, onecol_arg)
        else :
            print("Nothing I can do about, stay with twocolumn")
    elif col_set == "default" :
        if onecol_arg is not None :
            if hasoptbracket :
                print("adding %s into brackets"%onecol_arg)
                replaceAll(masterfile, "documentclass[", "documentclass["+onecol_arg+",")
            else :
                print("adding %s and brackets"%onecol_arg)
                replaceAll(masterfile, "documentclass", "documentclass["+onecol_arg+"]")
        else :
            print("Nothing I can do about, stay with default, maybe you are lucky")
    # need to remove any predefined geometry setttings.
    p = re.compile(r"^\\usepackage.*{geometry}")
    substituteAll(masterfile, p, "")
    # add geostr - to fit in the screen size of kindle DX
    p = re.compile(r"^\\begin{document}")
    if classname == "emulateapj" :
        subst = geostr_apj+fontstr+r"\\begin{document}"+magnifystr
    elif classname == "mn2e" :
        subst = geostr_mn+fontstr+r"\\begin{document}"+magnifystr
    elif classname == "elsarticle" :
        subst = geostr_els+fontstr+r"\\begin{document}"+magnifystr
    if classname == "aastex" or classname == "aastex6" :
        subst = geostr_aas+fontstr+r"\\begin{document}"+magnifystr
    elif classname == "old" :
        subst = r"\\begin{document}"+magnifystr
    else :
        subst = geostr+fontstr+r"\\begin{document}"+magnifystr
    substituteAll(masterfile, p, subst)
    # scale figures
    # if \includegraphics[width=xx]
    p = re.compile(r"\\includegraphics\[width=[\d|\.]+[cm|in|inch]+\]")
    subst = r"\includegraphics[width=1.0\\textwidth]"
    substituteAll(masterfile, p, subst)
    # scale figures, greedy fashion, hardly works
    # p = re.compile(r"[^a-zA-Z]width=[\d|\.]+[cm|in|inch]")
    # subst = r"width=1.0\\textwidth"
    # substituteAll(masterfile, p, subst)
    # not necessary
    # p = re.compile(r"\\begin{figure\*}")
    # subst = r"\\begin{figure}"
    # substituteAll(masterfile, p, subst)
    # p = re.compile(r"\\end{figure\*}")
    # subst = r"\\end{figure}"
    # substituteAll(masterfile, p, subst)
    # switch names for bbl files \bibliography{ref_hshwang}
    # change bbl to be named `bibmain`
    if bblname is None:
        pass
    else:
        p = re.compile(r"\\bibliography{\S+}")
        subst = r"\\bibliography{bibmain}"
        substituteAll(masterfile, p, subst)
    # comment out banned package
    for pack in banned_packages :
        p = re.compile("[^\%]usepackage(.*)\{" + pack +"\}")
        commentALL(masterfile, p)

def correct_unknown_author(pdffile) :
    """ ask input from commandline the true author name if the code cannot figure out.
    """

    if "unknown" in pdffile :
        true_author = ""
        while(true_author == ""):
            true_author = raw_input("The author name is obscure from the TeX file, please input the last name of the first author and press Enter.\n")
            if true_author == "" :
                print("Illegal input, author name can not be blank.")
            else :
                break
        newpdffile = pdffile.replace("unknown", true_author)
        shutil.move(pdffile, newpdffile)
        print("Corrected the pdf file name to %s" % newpdffile)
    else :
        newpdffile = pdffile
    return(newpdffile)
