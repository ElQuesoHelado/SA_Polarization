# IJACSA 2026: load the supplied class before the TeX distribution class.
# Run latexmk from the project root; use the same file at the Overleaf root.
use Cwd qw(abs_path);
use File::Spec;
my $sa_template_dir = abs_path('SAI_Paper_Format_Latex');
die "Missing supplied IJACSA class: SAI_Paper_Format_Latex/IEEEtran.cls\n"
    unless defined($sa_template_dir) && -f "$sa_template_dir/IEEEtran.cls";
my $sa_path_separator = ($^O eq 'MSWin32') ? ';' : ':';
$ENV{'TEXINPUTS'} = "$sa_template_dir//" . $sa_path_separator
    . ($ENV{'TEXINPUTS'} // '') . $sa_path_separator;
$pdf_mode = 1;
