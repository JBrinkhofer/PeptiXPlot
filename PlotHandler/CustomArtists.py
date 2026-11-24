from matplotlib.offsetbox import DraggableBase
from matplotlib.transforms import IdentityTransform, BboxTransformFrom
from matplotlib.text import Annotation
from matplotlib.lines import Line2D
from matplotlib import _docstring
import numpy as np
import functools

# Derived from matplotlib.offsetbox.py and matplotlib.text (Matplotlib 3.11.1).
# Copyright (c) 2012- Matplotlib Development Team; All Rights Reserved
# Changes: added PeptiXPlot blitting, custom picker behavior, custom artist
# state, and PeptiXPlot-specific offset updates and release handling.
# License: LICENSES/MATPLOTLIB_LICENSE.txt

class custom_DraggableBase(DraggableBase):
    """ A modified version of matplotlib.offsetbox.DraggableBase that allows for blitting using the blitting
        logic from PeptiXPlot, due avoid redraw on every mouse pick.
    """

    def __init__(self, ref_artist, use_blit=False):
        self.ref_artist = ref_artist
        if not ref_artist.pickable():
            ref_artist.set_picker(self._picker)
        self.got_artist = False
        self._use_blit = use_blit and self.canvas.supports_blit
        callbacks = self.canvas.callbacks
        self._disconnectors = [
            functools.partial(
                callbacks.disconnect, callbacks._connect_picklable(name, func))
            for name, func in [
                ("pick_event", self.on_pick),
                ("button_release_event", self.on_release),
                ("motion_notify_event", self.on_motion),
            ]
        ]

    @staticmethod
    def _picker(artist, mouseevent):
        # A custom picker so that picking is only possible with left mouse button
        if mouseevent.button == 1:
            return artist.contains(mouseevent)
        return False, {}
    
    def customBlit(self):
        self.ref_artist.master._blit_redraw(self.ref_artist.master.ax)

    def on_pick(self, evt):
        if self._check_still_parented():
            # Check for every single artist that is picked, whether multiple artists might have been picked too, if so, do not pick any additional artist
            if (evt.artist == self.ref_artist and 
                sum(1 for a in self.ref_artist.master.annotations + self.ref_artist.master.iannotations + self.ref_artist.master.manual_HPLC_baseline_axles 
                    if a._draggable is not None and a._draggable.got_artist) < 1):
                self.mouse_x = evt.mouseevent.x
                self.mouse_y = evt.mouseevent.y
                self.save_offset()
                self.got_artist = True
            
            if self.got_artist and self._use_blit:
                self.ref_artist.set_animated(True)
                # Remember if it was an inset annotation or a regular annotation
                inset = False
                # Remember whether it is an axle
                axle = False
                # Remove the artist from the annotations list, so it is not drawn
                collection = None
                if self.ref_artist in self.ref_artist.master.annotations:
                    self.ref_artist.master.annotations.remove(self.ref_artist)
                    collection = "annotations"
                elif self.ref_artist in self.ref_artist.master.iannotations:
                    self.ref_artist.master.iannotations.remove(self.ref_artist)
                    inset = True
                    collection = "iannotations"
                elif self.ref_artist in self.ref_artist.master.manual_HPLC_baseline_axles:
                    self.ref_artist.master.manual_HPLC_baseline_axles.remove(self.ref_artist)
                    self.ref_artist.master.skip_HPLC_baseline=True
                    axle = True

                self.customBlit()
                # Add the artist back to the correct annotations list
                if axle:
                    self.ref_artist.master.manual_HPLC_baseline_axles.append(self.ref_artist)
                    self.ref_artist.master.skip_HPLC_baseline=False
                elif collection == "annotations":
                    self.ref_artist.master.annotations.append(self.ref_artist)
                elif collection == "iannotations":
                    self.ref_artist.master.iannotations.append(self.ref_artist)
                
                fig = self.ref_artist.get_figure()
                # Copy this as the background for the annotation
                self.background = self.canvas.copy_from_bbox(fig.bbox)
                if axle:
                    self.ref_artist.master.HPLC_baseline.draw(fig._get_renderer())
                    for axle in self.ref_artist.master.manual_HPLC_baseline_axles:
                        axle.draw(fig._get_renderer())
                else:
                    self.ref_artist.draw(fig._get_renderer())
                self.canvas.blit()

# Derived from matplotlib.offsetbox.py and modified to work with
# custom_DraggableBase.

class custom_DraggableAnnotation(custom_DraggableBase):
    def __init__(self, annotation, use_blit=False):
        super().__init__(annotation, use_blit=use_blit)
        self.annotation = annotation

    def save_offset(self):
        ann = self.annotation
        anchor = ann.axes.transData.transform(ann.xy)
        offset = np.asarray(ann.xyann) * ann.figure.dpi / 72
        self.ox, self.oy = anchor + offset

    def update_offset(self, dx, dy):
        ann = self.annotation
        anchor = ann.axes.transData.transform(ann.xy)
        ann.xyann = (np.asarray((self.ox + dx, self.oy + dy)) - anchor) * 72 / ann.figure.dpi

class custom_DraggableLegend(custom_DraggableBase):
    def __init__(self, legend, use_blit=False):
        legend.set_picker(self._picker)
        super().__init__(legend, use_blit=use_blit)
        self.legend = legend

    def save_offset(self):
        renderer = self.legend.get_figure(root=True)._get_renderer()
        legend_box = self.legend._legend_box
        self.ox, self.oy = legend_box.get_offset(legend_box.get_bbox(renderer), renderer)
        legend_box.set_offset((self.ox, self.oy))

    def update_offset(self, dx, dy):
        self.legend._legend_box.set_offset((self.ox + dx, self.oy + dy))

    def on_release(self, event):
        if self._check_still_parented() and self.got_artist:
            renderer = self.legend.get_figure(root=True)._get_renderer()
            legend_box = self.legend._legend_box
            bbox = legend_box.get_bbox(renderer)
            ox, oy = legend_box._offset
            loc_in_canvas = (ox + bbox.x0, oy + bbox.y0)
            bbox_transform = BboxTransformFrom(self.legend.get_bbox_to_anchor())
            self.legend._loc = tuple(bbox_transform.transform(loc_in_canvas))
        super().on_release(event)

class custom_DraggableText(custom_DraggableBase):
    def __init__(self, text, use_blit=False):
        text.set_picker(self._picker)
        super().__init__(text, use_blit=use_blit)
        self.text = text

    def on_pick(self, event):
        if event.mouseevent.dblclick:
            return
        super().on_pick(event)

    def save_offset(self):
        self.ox, self.oy = self.text.get_transform().transform(self.text.get_position())

    def update_offset(self, dx, dy):
        position = self.text.get_transform().inverted().transform((self.ox + dx, self.oy + dy))
        self.text.set_position(position)

    def on_release(self, event):
        if self._check_still_parented() and self.got_artist:
            self.text.master.save_free_text_position(self.text)
        super().on_release(event)
    
class custom_Annotation(Annotation):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.background = None # This will hold the background for blitting, the background will be passed from Plotter.py

    # Derived from matplotlib.text._AnnotationBase and modified to work with
    # PeptiXPlot's background blitting logic.
    def draggable(self, state=None, use_blit=False):
        """
        Set whether the annotation is draggable with the mouse.

        Parameters
        ----------
        state : bool or None
            - True or False: set the draggability.
            - None: toggle the draggability.
        use_blit : bool, default: False
            Use blitting for faster image composition. For details see
            :ref:`func-animation`.

        Returns
        -------
        custom_DraggableAnnotation or None
            If the annotation is draggable, the corresponding
            `.custom_DraggableAnnotation` helper is returned.
        """
        is_draggable = self._draggable is not None

        # if state is None we'll toggle
        if state is None:
            state = not is_draggable

        if state:
            if self._draggable is None:
                self._draggable = custom_DraggableAnnotation(self, use_blit)
                self._draggable.background = self.background
        else:
            if self._draggable is not None:
                self._draggable.disconnect()
            self._draggable = None

        return self._draggable

class custom_DraggableDot(custom_DraggableBase):
    def __init__(self, dot, use_blit=False):
        super().__init__(dot, use_blit=use_blit)
        self.dot = dot

    def save_offset(self):
        dot = self.dot
        self.ox, self.oy = dot.get_transform().transform(dot._xy[0])
        dot.count = dot.xpoints.index(dot._xy[0][0])

    def update_offset(self, dx, dy):
        dot = self.dot
        (x, y) = dot.get_transform().inverted().transform((self.ox + dx, self.oy + dy))
        dot.set_data(([x], [y]))
        dot.xpoints[dot.count] = x
        dot.ypoints[dot.count] = y

        # Dots should not occur twice at the exactly same position. If they do, give them a small offset
        while dot.xpoints.count(x) > 1:
            index = dot.xpoints.index(x)
            if index == dot.count:
                index = dot.xpoints.index(x, index+1)
            dot.xpoints[index] -= 10**-12
        while dot.ypoints.count(y) > 1:
            index = dot.ypoints.index(y)
            if index == dot.count:
                index = dot.ypoints.index(y, index+1)
            dot.ypoints[index] -= 10**-12

        # Check the new order
        pairs = sorted(zip(dot.xpoints,
                           dot.ypoints))

        xpoints_sorted, ypoints_sorted = map(list, zip(*pairs))
        # Only update the items not the object they are referencing
        dot.xpoints[:] = xpoints_sorted
        dot.ypoints[:] = ypoints_sorted
        # Update count
        dot.count = dot.xpoints.index(x)
        
    def on_motion(self, evt):
        super().on_motion(evt)
        dot = self.dot
        if self._check_still_parented() and self.got_artist and self._use_blit:
            baseline_x_data = self.ref_artist.master.HPLC_baseline.get_xdata()
            baseline_y_data = self.ref_artist.master.HPLC_baseline.get_ydata()
            # This needs to be plus one because of the points inserted at xmin and xmax
            baseline_x_data[1:-1] = dot.xpoints
            baseline_y_data[1:-1] = dot.ypoints
            # If count == 0, 1 or count == len(xpoints)-1, -2 also change the xmin / xmax points to be correct
            if dot.count in [0, 1]:
                # Add two points to the HPLC_baseline, one that is always at xmin and one that is always at xmax
                xmin = dot.xmin
                
                # For the y_coordinate of ymin, take the first and second axle, calculate m and b (y = mx + b)
                (axle_0_x, axle_0_y) = (dot.xpoints[0],dot.ypoints[0])
                (axle_1_x, axle_1_y) = (dot.xpoints[1],dot.ypoints[1])

                m = (axle_1_y-axle_0_y)/(axle_1_x-axle_0_x)
                b = axle_0_y - m * axle_0_x

                ymin = m * xmin + b

                baseline_x_data[0] = xmin
                baseline_y_data[0] = ymin

            elif dot.count in [len(dot.xpoints)-1, len(dot.xpoints)-2]:
                xmax = dot.xmax
                # For the y_coordinate of xmax, take the last and second to last axle, calculate m and b (y = mx + b)
                axle_last_x, axle_last_y = (dot.xpoints[-1],dot.ypoints[-1])
                axle_2nd_last_x, axle_2nd_last_y = (dot.xpoints[-2],dot.ypoints[-2])

                m = (axle_2nd_last_y-axle_last_y)/(axle_2nd_last_x-axle_last_x)
                b = axle_last_y - m * axle_last_x

                ymax = m * xmax + b

                baseline_x_data[-1] = xmax
                baseline_y_data[-1] = ymax

            self.ref_artist.master.HPLC_baseline.set_data(baseline_x_data, baseline_y_data)
            self.ref_artist.master.ax.draw_artist(self.ref_artist.master.HPLC_baseline)
            for axle in self.ref_artist.master.manual_HPLC_baseline_axles:
                self.ref_artist.master.ax.draw_artist(axle)
            self.canvas.blit()


class custom_Dot(Line2D):
    def __init__(self, xdata: float, ydata: float, *args, **kwargs):

        super().__init__(xdata=xdata, ydata=ydata, *args, **kwargs)
        self.background = None # This will hold the background for blitting, the background will be passed from Plotter.py
        self._draggable = None

    # Derived from matplotlib.text._AnnotationBase and modified to work with
    # PeptiXPlot's background blitting logic.
    def draggable(self, state=None, use_blit=False):
        """
        Set whether the Dot is draggable with the mouse.

        Parameters
        ----------
        state : bool or None
            - True or False: set the draggability.
            - None: toggle the draggability.
        use_blit : bool, default: False
            Use blitting for faster image composition. For details see
            :ref:`func-animation`.

        Returns
        -------
        custom_DraggableDot or None
            If the Dot is draggable, the corresponding
            `.custom_DraggableDot` helper is returned.
        """
        is_draggable = self._draggable is not None

        # if state is None we'll toggle
        if state is None:
            state = not is_draggable

        if state:
            if self._draggable is None:
                self._draggable = custom_DraggableDot(self, use_blit)
                self._draggable.background = self.background
        else:
            if self._draggable is not None:
                self._draggable.disconnect()
            self._draggable = None

        return self._draggable


@_docstring.interpd
def annotate(self, text, xy, xytext=None, xycoords='data', textcoords=None,
             arrowprops=None, annotation_clip=None, **kwargs):
    # Signature must match Annotation. This is verified in
    # test_annotate_signature().
    a = custom_Annotation(text, xy, xytext=xytext, xycoords=xycoords,
                         textcoords=textcoords, arrowprops=arrowprops,
                         annotation_clip=annotation_clip, **kwargs)
    a.set_transform(IdentityTransform())
    if kwargs.get('clip_on', False) and a.get_clip_path() is None:
        a.set_clip_path(self.patch)
    self._add_text(a)
    return a
annotate.__doc__ = custom_Annotation.__init__.__doc__
#### Lines and spans

