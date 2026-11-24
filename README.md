# **PeptiXPlot**

PeptiXPlot is an open-source graphical user interface for organizing and plotting common types of peptide-related experimental data.

PeptiXPlot is a Tkinter-based graphical user interface built around Matplotlib and tailored to peptide research. It currently supports CD spectra, temperature-dependent CD profiles, fluorescence and UV/vis spectra, (U)HPLC chromatograms, MALDI mass spectra, and Michaelis-Menten kinetics.

# **Table of Contents**

- [Installation](#installation)
    - [Distribution and third-party licenses](#distribution-and-third-party-licenses)
- [User Guide](#user-guide)
    - [General layout](#general-layout)
        - [Menu Bar](#menu-bar)
        - [File Browsers](#file-browsers)
        - [GUI Plot](#gui-plot)
        - [Plot Information](#plot-information)
        - [Plot Settings](#plot-settings)
    - [File Import](#file-import)
        - [Basic Import](#basic-import)
        - [Advanced Import](#advanced-import)
    - [Settings](#settings)
        - [General Settings](#general-settings)
        - [Assay-specific Settings](#assay-specific-settings)
        - [CD-specific Settings](#cd-specific-settings)
        - [MALDI-specific Settings](#maldi-specific-settings)
        - [Temperature-dependent CD profile (Tm)-specific Settings](#temperature-dependent-cd-profile-tm-specific-settings)
    - [Supported Plots](#supported-plots)
        - [General Plot Settings](#general-plot-settings)
        - [CD Spectra](#cd-spectra)
        - [Temperature-dependent CD Profiles (Tm)](#temperature-dependent-cd-profiles-tm)
        - [Fluorescence and UV/vis Spectra](#fluorescence-and-uvvis-spectra)
        - [HPLC Chromatograms](#hplc-chromatograms)
        - [MALDI Mass Spectra](#maldi-mass-spectra)
        - [Michaelis-Menten Kinetics](#michaelis-menten-kinetics)
        - [MultiPlots](#multiplots)
- [How to cite](#citation)

# **Installation**

PeptiXPlot currently requires Python 3.12.

Open a terminal in the directory in which you want to install PeptiXPlot. Then execute the following commands:

```text
git clone https://github.com/JBrinkhofer/PeptiXPlot
cd PeptiXPlot
pip install -r requirements.txt
```

To start the application from a local checkout, run `PeptiXPlot.py` with Python.

## **Distribution and licenses**

PeptiXPlot's own source code is licensed under the [MIT License](LICENSE).
Third-party notices do not replace the project's own license.
Include the complete [LICENSES/](LICENSES/) directory in every distribution. It contains the full Matplotlib license text. 

The PNG files under `icons/` were created by Julian Brinkhofer and are covered by PeptiXPlot's MIT license.

# **User Guide**

When PeptiXPlot is started for the first time, it creates an `assets` folder containing the configuration file and the SQLite database used by the application.

## **General layout**

The graphical user interface is divided into five main regions:

1. The menu bar is at the top.
2. The file browser is on the left.
3. The plot is in the center.
4. Plot information, including picked peaks, selected integrals, and fits for temperature-dependent CD plots, is shown at the bottom.
5. Plot settings are shown on the right.

### **Menu Bar**

The menu bar contains the options `File` and `Help`.

Under `File`, you can create project folders, MultiPlots, and Assays. You can also import experimental data with `Open Files`. New file-browser items are created as children of the current selection when the selected item is a project folder.

`Save`, `Save as...`, and `Save all` export the selected plot or all plots according to the export settings. `Import PeptiXPlot Files` imports a PeptiXPlot (`.pxp`) file, which is a compressed, serialized JSON file. `Export Selected Plots` exports the selected items from both the `Experimental Files` and `MultiPlots / Assays` browsers, including their folder structure and dependencies, as a `.pxp` file in the selected location.

`Settings` opens the settings window. There you can configure general plot settings, such as plot size, line width, and color, as well as export settings, such as DPI and the default export directory.

Under `Help`, you can find links to the GitHub repository and the local documentation.

### **File Browsers**

PeptiXPlot has two file browsers arranged as notebook tabs:

- The `Experimental Files` browser contains experiments imported with `Open Files`.
- The `MultiPlots / Assays` browser contains plots created from experiments in the `Experimental Files` browser.

Each browser has a context menu with options such as creating project folders, cutting, copying, pasting, renaming, and deleting items. The `Experimental Files` browser also allows you to open files and assign a blank to the selected items. The `MultiPlots / Assays` browser provides options for creating MultiPlots and Assays.

Both browsers use natural sorting through `natsort` and have their own search bar. Items can be reorganized by drag and drop, files can be loaded by dragging them into the appropriate location, and experimental files can be added to Assays or MultiPlots by dragging them into the corresponding treeview.

### **GUI Plot**

The plot area displays a lower-resolution, real-time preview of the exported figure. A Matplotlib toolbar above the plot has been adapted for PeptiXPlot and provides tools for peak picking, integration, and creating free text at a user-defined position. The cursor coordinates are displayed when the pointer is moved over the plot.

The button next to the plot allows you to choose a blank measurement for the current experiment. Annotations created with peak picking or free text can be edited in the preview by double-clicking them and moved by dragging them. When an annotation is moved away from its original position, an arrow points to the picked peak.

By default, Matplotlib's mathtext engine parses annotation text. When `Recognize super- and subscripts` is enabled, `^` places the following letter in superscript and `_` places the following letter in subscript. If `{}` immediately follows either symbol, the complete expression inside the braces is formatted. When `Recognize super- and subscripts` is disabled, use standard mathtext notation. Pressing Shift+Enter while editing text creates a line break.

### **Plot Information**

For HPLC chromatograms, the bottom treeview shows picked integrals, their positions and areas, and their percentages of the total integrated peak area. Double-click the `Include?` entry to include or exclude an integral from the percentage calculation.

For fluorescence, UV/vis, and MALDI spectra, the bottom treeview shows picked peaks and their labels. For MALDI spectra, it also allows you to enter a suspected molecular formula and simulate a spectrum with `molmass`. N- and C-caps can be specified using notation such as `Ac-CDEFGHIKLMNPRSTWY-NH2`. You can also enter the suspected charge, the intensity relative to the largest peak, and the full width at half maximum for spectrum simulation.

For temperature-dependent CD measurements, the bottom treeview shows the available fits and the fit selected for the current figure. Double-click a fit to select it.

For MultiPlots, the bottom treeview lists the experimental files in the MultiPlot, their legend labels, and the color, line width, line style, alpha value, and position of each line. Add experimental files by dragging them from the `Experimental Files` browser. Edit line-related settings by double-clicking the corresponding entry. Positions determine the drawing order: the highest position is drawn first and the lowest position is drawn last. Positions can be edited directly or changed by dragging.

For Assays, which currently support only Michaelis-Menten kinetics, the bottom treeview shows the grouped data points, the x- and y-coordinates of each data point, and the coefficient of determination and relative quantitative nonlinearity of the linear regression for each experimental file. Double-click a measurement to inspect its linear fit. Data points can be renamed and their x-coordinates changed by double-clicking. Experimental files can be reorganized by dragging them, and new files can be added from the `Experimental Files` browser.

### **Plot Settings**

The plot settings are shown on the right. At the top, the label of the currently loaded figure is displayed, with its directory in italics below it. The available settings depend on the current plot type.

General settings, such as the x- and y-axis limits, line style, and line color, are shown at the top. Tick settings are shown below them. Collapsible frames contain plot-specific settings, described in the [Supported Plots](#supported-plots) section. Every plot also has a notepad at the bottom of the plot settings frame and an export button for quick figure export.

## **File Import**

PeptiXPlot provides two import modes. Use basic import for simple files, such as `.csv` files with x and y values in the first two columns and a specified separator. Use advanced import for more complex files, such as `.xlsx` files or `.csv` files containing multiple columns.

Open the import window through `File > Open Files`, the context menu in the `Experimental Files` browser, or the Ctrl+O shortcut. Select the plot type before importing, regardless of the import mode. Import is generally performed with pandas, with NumPy's `genfromtxt` used as a fallback. If an import fails, check the terminal for diagnostic information and correct the import settings.

### **Basic Import**

- `Presets`: Create and use import presets in basic import mode. The default preset cannot be renamed or deleted. `Save as...` saves the current settings as a new preset. Enter the new name in the name field before selecting `Save as...`, or enter it in the dialog that appears. Preset names must be unique. Save changes to a preset with `Save`, or save them automatically by selecting `Choose Files`.
- `Separator`: The separator between x and y values in the file.
- `Decimal delimiter`: The decimal delimiter used in the file.
- `Values start in line" / "Values end in line`: The inclusive, one-based line range to read.
- `End at a specific line`: Leave this option disabled when the file has no footer. The importer then reads the file from the line specified by `Values start in line` to the end of the file.
- `Choose Files`: Continue to file selection using the current import settings.

### **Advanced Import**

- `Preview File`: Select a file to preview when using advanced import. Changes to the import settings are applied in real time.
- `Datasheet`: For `.xlsx` files, select the worksheet from which to import values.
- `Separator" and "Decimal`: See [Basic Import](#basic-import).
- `Transpose Dataframe`: Transpose the entire spreadsheet. The x and y values must still be in two columns when imported.
- `Spreadsheet`: Select the values to import in the spreadsheet displayed at the bottom of the window. The selected values do not need to be adjacent, but they must come from two columns and both selections must have the same size. Alternatively, select one two-column range. Rows containing missing values can be omitted.
- `Confirm Selection`: Open a confirmation window where you can add a suffix to imported files, switch the axes if the x and y values are reversed, and inspect the dataframe to be imported. `Import File` imports only the previewed file. `Import Multiple Files` opens a file browser for selecting additional files to import with the same settings.

## **Settings**

Open the settings window through `File > Settings`. Changes made under `General` also affect plot types that share the same setting. Use the arrow next to `Apply` to apply changes to all plot types. `Ok` saves the settings and closes the window, while `Cancel` closes it without saving. `Reset` restores the default configuration.

### **General Settings**

- `Plot size`: The width and height of the axes in inches.
- `Edge padding`: The padding between the plot and the figure border. Plot size plus edge padding gives the figure size.
- `Label on x-axis" / "Label on y-axis`: The labels displayed on the respective axes.
- `Linewidth`: The line width, or the marker size when a line width is not applicable.
- `Color`: The color of the plotted line. Select the colored rectangle to change it.
- `Font`: The font used in the figure. `sans serif` is Matplotlib's standard and can differ between systems.
- `Fontsize`: The font size used in the figure.
- `Recognize super- and subscripts`: Automatically interpret `^` and `_` in annotations and free text. If disabled, use mathtext exactly as described in the Matplotlib documentation.
- `DPI`: The resolution of exported figures in dots per inch.
- `Filetype`: The file format used for exported figures.
- `Transparent`: Export figures with a transparent background.
- `Allow duplicates on export`: When enabled, exporting a figure does not overwrite an existing file with the same name. Instead, a number is appended to the new file name.
- `Export directory`: The default directory for exported figures.
- `Enable dark mode`: Enable dark mode for the GUI, except for the figure.
- `Enable color-blind mode`: Replace hard-coded red with an orange shade from the Okabe-Ito color palette.

### **Assay-specific Settings**

- `Assay type`: Select the assay type to which the settings apply. This currently affects the axis labels.
- `Color of fit`: The color of the fit line.

### **CD-specific Settings**

- `MRE label on y-axis`: The label displayed when mean residue ellipticity is shown.

### **MALDI-specific Settings**

- `Color of simulation`: The color of the simulated spectrum.

### **Temperature-dependent CD profile (Tm)-specific Settings**

- `MRE label on y-axis`: The label displayed when mean residue ellipticity is shown.
- `Derivative label on y-axis`: The label displayed when the derivative of the measured ellipticity is shown.
- `MRE derivative label on y-axis`: The label displayed when the derivative of the mean residue ellipticity is shown.
- `Color of fit`: The color of the fit line.

## **Supported Plots**

The following sections describe general options and plot-specific settings. These settings apply to the currently open plot.

### **General Plot Settings**

All plots generally provide the following settings.

**Plot Settings**

- `Span of x-Axis`: The visible x-axis limits.
- `Auto-adjust y-Axis`: Automatically adjust the y-axis to the visible data. For CD spectra, temperature-dependent CD profiles, and Assays, both y-axis limits are adjusted. For fluorescence, HPLC, MALDI, and UV/vis spectra, only the lower y-axis limit is adjusted.
- `Span of y-Axis`: The visible y-axis limits. When the pointer is over the figure, scrolling changes the upper limit for fluorescence, HPLC, MALDI, and UV/vis spectra, and both limits for other plot types. Scrolling is disabled for MultiPlots and Assays.
- `Linestyle`: The line style of the main line. Select a style from the dropdown menu or use Matplotlib tuple notation for precise control.
- `Color`: The color of the main line.
- `Vertical Labels`: Display annotation labels vertically or horizontally.
- `Baseline Smoothing`: Select a baseline-smoothing method. Smoothing is performed before baseline correction and blank subtraction. Available methods include:
  - Savitzky-Golay smoothing, implemented with `scipy.signal.savgol_filter`
  - Whittaker smoothing, implemented with `scipy.signal.whittaker_henderson`
  - Finite impulse response low-pass filtering, implemented with `scipy.signal.firwin` and `scipy.signal.filtfilt`
  - Wavelet filtering, implemented with PyWavelets (`pywt`)
  - Sparsity-assisted signal smoothing, implemented with NumPy according to *Sparsity-assisted signal smoothing (revisited)* [I. Selesnick, in *2017 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)*, **2017**, pp. 4546-4550.]
- `Baseline Correction`: Select a baseline-correction algorithm. Correction is performed after baseline smoothing and before blank subtraction. Available methods include:
  - asLS (asymmetric least squares), implemented with `pybaselines.Baseline.asls`
  - airPLS (adaptive iteratively reweighted penalized least squares), implemented with `pybaselines.Baseline.airpls`
  - arPLS (asymmetrically reweighted penalized least squares), implemented with `pybaselines.Baseline.arpls`
  - Mixture Model, implemented with `pybaselines.Baseline.mixture_model`
  - Backcor, implemented with `pybaselines.Baseline.penalized_poly`
  - Local Minimum Values (coupled with robust statistical analysis, LMV-RSA), implemented with NumPy according to *Simple automatic strategy for background drift correction in chromatographic data analysis* [H.-Y. Fu, H.-D. Li, Y.-J. Yu, B. Wang, P. Lu, H.-P. Cui, P.-P. Liu, Y.-B. She, *J. Chromatogr. A* **2016**, *1449*, 89-99.]

**Tick Settings**

- `Show Ticks on x-Axis`: Display ticks on the x-axis.
- `Distance of Major x-Ticks`: The distance between major ticks.
- `Offset of Major x-Ticks`: The offset from zero for all major ticks.
- `Number of Minor x-Ticks`: The number of minor ticks between consecutive major ticks.
- `y-Axis`: The y-axis has the corresponding tick settings.

### **CD Spectra**

- **General:** Plot CD spectra using either measured ellipticity or mean residue ellipticity. For mean residue ellipticity, enter the cuvette path length, sample concentration, and number of backbone amides. You can also display and customize a constant line at `y = 0`.
- `Calculate MRE`: Use mean residue ellipticity on the y-axis.
- `Sample Parameters`: Enter the path length, sample concentration in mM, and number of backbone amides.
- `Zero-Constant Settings`: Configure the constant line at `y = 0`, including its color, line width, and line style. Select a line style from the dropdown menu or use Matplotlib tuple notation.

### **Temperature-dependent CD Profiles (Tm)**

- **General:** Plot temperature-dependent CD profiles using measured ellipticity, mean residue ellipticity, or their derivatives. The application can perform and display basic sigmoidal fits, fit the Van't Hoff equation, and perform an empirical Gaussian fit on the profile derivative. The melting temperature (the midpoint of the folding-to-unfolding transition) and molar enthalpy are reported. The baselines of sigmoidal fits can also be displayed as dashed lines in the fit color.
- `Calculate MRE`: Use mean residue ellipticity on the y-axis.
- `Sample Parameters`: Enter the path length, sample concentration in mM, number of backbone amides, and measurement wavelength. The wavelength can be included in the y-axis label by adding `VAR_wavelength` to the label. A CD spectrum can also serve as a blank for a temperature-dependent CD profile; in that case, PeptiXPlot uses the value at the specified wavelength for blank subtraction.
- `Perform Curve Fit`: Perform all five available fits using the current settings. Changing sample parameters changes the baseline positions because it changes the scaling. Reperform the fits after switching between measured and mean residue ellipticity or changing sample parameters.
- `Show Fit`: Display the selected fit in the figure.
- `Show Baselines`: Display the baselines of the sigmoidal fits, when applicable.
- **Choosing a Fit:** Double-click an entry in the bottom treeview to display that fit. `A` and `B` are the approximated baselines of the unfolded and folded states, respectively.

### **Fluorescence and UV/vis Spectra**

- **General:** Plot fluorescence and UV/vis spectra. Use the peak-picking tool in the toolbar to pick and annotate peaks.

### **HPLC Chromatograms**

- **General:** Plot and analyze (U)HPLC chromatograms. Use the peak-picking and integration tools in the toolbar to pick, annotate, and integrate peaks. PeptiXPlot provides several integration methods.
- **Peak List:** The peak list is shown in the right frame. Select a peak and press Delete to remove it. Change labels by double-clicking an entry in the peak list or the annotation in the figure; editing the annotation directly is recommended. Insert line breaks with `\n` or with Shift+Enter while editing an annotation. Super- and subscripts work as described in [GUI Plot](#gui-plot).
- **Integration Settings:** Configure how integration is performed.
  - `Show Integrated Areas`: Display the polygons used for integration. Integration uses `scipy.integrate.trapezoid`.
  - `Approximate Locally`: Give each peak its own baseline, approximated as a straight line between the first and last data points in the integral.
  - `Approximate Linear Baseline`: Approximate one baseline for all integrals as a straight line through the two x-values specified below.
  - `Approximate Constant Baseline`: Approximate the baseline as a horizontal line at the specified y-value.
  - `Pick Baseline Manually`: Select the baseline manually. Select `Toggle Baseline` to display a red line, or an orange line in color-blind mode, with white draggable points. Double-click the baseline to add a point and right-click a point to delete it.
- **Integral List:** The bottom treeview lists each integral's limits, center, area, and percentage of the total measured area. Double-click its `Include?` entry to exclude an integral from the percentage calculation. Press Delete to remove an integral.

### **MALDI Mass Spectra**

- **General:** Plot and analyze mass spectra. PeptiXPlot was developed and tested specifically with MALDI mass spectra, although other types, such as ESI spectra, should also work. Deconvolution and LC-MS data are not currently supported. Use the peak-picking tool to pick and annotate peaks. PeptiXPlot can simulate spectra with `molmass` and add an inset to highlight a selected region.
- **Inset Settings:** Configure the inset location, size, and displayed region.
  - `Draw Inset`: Display an inset in the figure.
  - `Span of x-Axis`: Set the inset's x-axis limits.
  - `Height of y-Axis`: Set the relative y-axis height with respect to the global maximum.
  - `Inset Position`: Select the inset position from the dropdown menu.
  - `Width" / "Height`: Set the relative inset dimensions in axes coordinates.
  - `Border Pad`: Set the padding around the inset. A float applies equal padding on both sides; a tuple `(width_pad, height_pad)` sets the dimensions independently.
  - `Fontsize`: Set the font size of all text objects in the inset.
  - `Mirror Annotations`: Mirror annotations from the main axes. Annotations can also be picked separately in the inset. In the peak list, annotations inside the inset are prefixed with `i:`.
  - `Vertical Labels`: Display annotation labels vertically or horizontally.
- **Peak List:** Edit labels by double-clicking the entry or the label in the figure. Enter a suspected molecular formula using any notation supported by `molmass`; peptide and protein N- and C-caps can also be specified, for example `Ac-GFAFGG-NH2`. The monoisotopic mass is displayed in the treeview. Change the expected ion charge, relative intensity, and full width at half maximum by double-clicking the corresponding entries. Double-click `Simulate?` to plot the simulated spectrum. Press Delete to remove peaks from the figure.

### **Michaelis-Menten Kinetics**

- **General:** Create a Michaelis-Menten plot in the `MultiPlots / Assays` browser by creating a new Assay and setting its assay type to `Michaelis-Menten`. This is currently the only supported assay type.

  Add each initial-rate measurement to the `Experimental Files` browser as a `Kinetics` measurement. Preferably, include the substrate concentration and repeat number in each file name, for example `XY001_0.1mmol/l_1` and `XY001_0.1mmol/l_2`. PeptiXPlot recognizes common concentration notations such as `mM`, `millimolar`, and `mmol/l`. For micromolar concentrations, `u` can be used instead of `µ`. The application groups repeats and extracts the concentration from the file name when possible; you can also group files manually.
- **Assay Settings:**
  - `Pick Assay`: Select the assay type. Currently, only `Michaelis-Menten` is supported.
  - `Mol. Abs. Coefficient`: The molar absorption coefficient used to convert the initial rate to the desired unit.
  - `Unit on x-Axis`: The unit displayed on the x-axis. The application adjusts it when values or data points are changed.
  - `x-Axis Label`: The x-axis label, which defaults to the label specified in the settings.
  - `Unit on y-Axis`: The unit displayed on the y-axis. The application adjusts it when values or data points are changed.
  - `y-Axis Label`: The y-axis label, which defaults to the label specified in the settings.
  - `Automatically Sort Files`: Automatically group experimental files based on the similarity of their names.
- **Fit Settings:**
  - `Show Fit`: Display the fit line.
  - `Color`: The fit-line color.
  - `Linewidth`: The fit-line width.
  - `Linestyle`: The fit-line style. Select a style from the dropdown menu or use Matplotlib tuple notation.
  - `Fit Parameters`: Display the Michaelis-Menten fit parameters: `Vmax`, `Km`, and the coefficient of determination.
  - `Show Vmax Constant`: Display a constant line at `y = Vmax`.
  - `Show Km Rectangle`: Display a rectangle highlighting `Km` and `Vmax / 2`.
  - `Show Fit Parameters`: Display the fit parameters in a legend inside the figure.
- **Adding data points:** Add each initial-rate measurement to the `Experimental Files` browser as a `Kinetics` measurement. Drag the measurements into the bottom treeview. PeptiXPlot calculates the initial rate by linear regression. When `Automatically Sort Files` is enabled, files are grouped by name similarity and their concentrations are extracted from their names when possible. With every change, the data is fit to the Michaelis-Menten equation. If all data points include replicates, then a weighted fit is performed using the standard error of the mean for each data point. If all data points contain just one measurement, a weighted fit is performed using the standard deviation of the initial rate linear regression. If data points use mixed statistical measures, the error bars are still shown using those measures but an unweighted fit is performed. Generally, it is advisable to always perform and include replicate measurements.
- **Data-point treeview:** Measurements are grouped into data points. The treeview shows each data point's x- and y-coordinates and the standard error of the mean if a data point includes replicates. Otherwise, the standard deviation of the initial rate fit for the single measurement it contains is shown. For a data point with one measurement, the standard deviation of the linear fit to that measurement is used. Expand a data point with the plus button to see its measurements. Each measurement shows its initial rate, the standard deviation of its linear fit, the coefficient of determination, and the relative quantitative nonlinearity described by Emancipator and Kroll (1993). Double-click a measurement to inspect its linear and nonlinear fits. Rename data points and change their x-coordinates by double-clicking. Move measurements between data points by dragging them. Add or remove data points and measurements using the context menu or Delete.

### **MultiPlots**

- **General:** MultiPlots contain multiple spectra or chromatograms, either superimposed or stacked. Create one in the `MultiPlots / Assays` browser with `New MultiPlot` or the Ctrl+Shift+N shortcut. Add plots from `Experimental Files` by dragging them into the bottom treeview. All plots in a MultiPlot must have the same plot type. General plot settings are taken from the plot type used by the MultiPlot.
- `Min-Max Normalization`: Normalize each curve so that its minimum is 0 and its maximum is 1. This is useful for qualitative comparisons.
- `Offset Plots`: Stack spectra and chromatograms with an offset when enabled; otherwise, superimpose them.
- `Labels`: Configure how plots are labeled. The available options are `In Axes`, `In Legend`, and `Hide`. `In Axes` is available only for offset plots and places a label above each line. Change the position relative to the line in `Label Settings`.
- **Label Settings:**
  - `Automatically Place Legend`: Let Matplotlib choose the legend position. Moving the legend manually disables this option.
  - `Legend Transparency`: Set the legend transparency, where 1 is fully transparent.
  - `Match Color`: When labels are placed in the axes, match the label color to the line color; otherwise, use black.
  - `x-Position" / "y-Position`: Set the relative position of an axes label.
  - `Fontsize`: Set the font size of labels or the legend.
- `Apply Colormap`: Apply a Matplotlib colormap to the current figure according to the position numbers in the bottom treeview.
- `3D MultiPlot`: Convert the MultiPlot to a three-dimensional plot and display additional `3D Plot Settings`.
- **3D Plot Settings:**
  - `Elevation`: The elevation of the 3D projection.
  - `Azimuth`: The azimuth of the 3D projection.
  - `Offset of Plots`: The y-axis distance between plots in the 3D projection.
  - `Perspective Mode`: Use perspective or orthographic projection. See the Matplotlib documentation for details.
- **File treeview:** The bottom treeview lists plots in the MultiPlot. Add and reorganize plots by dragging them. Change labels, colors, line widths, line styles, alpha values, and positions by double-clicking the corresponding entries. Select a line style from the dropdown menu or use Matplotlib tuple notation. Press Delete to remove plots; the remaining plots are repositioned to fill gaps.

# **Citation**

Citation information will be added upon publication.
