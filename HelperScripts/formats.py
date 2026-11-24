
from matplotlib import mathtext
import logging
from math import floor, log10

DEBUG = False

def normalize_rgb_tuple(rgb_tuple):

    if len(rgb_tuple)<3: return

    elif len(rgb_tuple) == 3:

        r, g, b = rgb_tuple

        return (r/255, g/255, b/255)

    elif len(rgb_tuple) == 4:

        r, g, b, a = rgb_tuple
        
        return (r/255, g/255, b/255, a/255)

def return_regular_rgb_tuple(rgb_tuple):

    if len(rgb_tuple)<3: return

    elif len(rgb_tuple) == 3:
        r, g, b = rgb_tuple

        return (int(r*255), int(g*255), int(b*255))

    elif len(rgb_tuple) == 4:
        r, g, b, a = rgb_tuple

        return (int(r*255), int(g*255), int(b*255), int(a*255))

class GlyphFilter(logging.Filter):
    def filter(self, record):
        return "does not have a glyph for" not in record.getMessage()

def is_mathtext_valid(label, dpi=150, prop=None):
    parser = mathtext.MathTextParser("path")
    try:
        parser.parse(label, dpi=dpi, prop=prop)
        return True
    except Exception as e:
        print(f"Mathtext is invalid: {e}")
        return False    


def autoscripts(label, automatic_scripts):
    # modify label, so it can be integrated well in the plot. Start with replacing escaped next line with actual next line assignment
    label = label.replace("\\n","\n")
    
    if automatic_scripts:
        for mark in ["_","^"]:
            # find an underscore in the string, to make subscripts
            sub = label.find(mark)
            dollar1 = label.find("$")
            dollar2 = label.find("$",dollar1+1)
            while sub != -1 and sub < len(label)-1:
                # Check whether sub is already inbetween two dollar signs, if so, skip logic
                if not (dollar1 != -1 and dollar2 != -1 and dollar1 < sub and dollar2 > sub):
                    # First check whether an _ or ^ is escaped with \ or whether it already has a prepending dollar sign
                    if sub-1 > -1 and label[sub-1] not in ["\\","$"]:

                        # check if the following value is in brackets {}
                        if label[sub+1] == "{":
                            bracket = label.find("}",sub+1)
                            if bracket != -1:
                                label = label[:sub]+"$"+mark+label[sub+1:bracket+1]+"$"+label[bracket+1:]
                        else:
                            # make the subscript at the position of the underscore
                            label = label[:sub]+"$"+mark+label[sub+1]+"$"+label[sub+2:]

                    elif label[sub-1] == "\\":
                        label = label[:sub-1]+label[sub:]
                
                sub = label.find(mark,sub+2)
                dollar1 = label.find("$",max(dollar2+1, sub+2))
                dollar2 = label.find("$",dollar1+1)

    if not is_mathtext_valid(label):
        label = label.replace("$","")
        print("Removing all $")

    return label

def autoscripts_reverse(label, automatic_scripts):

    if automatic_scripts:
        # First check whether there is a _ or ^ that does not have a $ before
        # Just as in autoscripts, check whether _ or ^ are not part of a larger mathtext expression
        # find all sub- and superscripts
        for mark in ["_","^"]:
            index = label.find(mark)
            dollar1 = label.find("$")
            dollar2 = label.find("$",dollar1+1)
            while index != -1:
                # First check whether an _ or ^ was escaped with \, 
                # also check here whether it is not part of a larger mathtext expression
                if index-1 > -1 and label[index-1] != "$" and not (dollar1 != -1 and dollar2 != -1 and dollar1 < index and dollar2 > index):
                    label = label[:index]+"\\"+label[index:]
                
                # Otherwise do logic to specifically remove only mathtext expressions surrounding underscores
                else:
                    if label[index-1] == "$":
                        # find second dollar sign
                        second_dollar = label.find("$",index)
                        if second_dollar != -1:
                            label = label[:index-1]+label[index:second_dollar]+label[second_dollar+1:]
                
                index = label.find(mark,index+2)
                dollar1 = label.find("$",max(dollar2+1, index+2))
                dollar2 = label.find("$",dollar1+1)

    return label

logger = logging.getLogger("matplotlib.mathtext")
logger.addFilter(GlyphFilter())