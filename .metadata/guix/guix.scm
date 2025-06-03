;; This file is generated automatically from metadata
;; File edits may be overwritten!
(use-modules
 (guix packages)
 (guix git-download)
 (guix gexp)
 ((guix licenses) #:prefix license:)
 (guix build-system python)
 (gnu packages base)
 (gnu packages emacs)
 (gnu packages emacs-xyz)
 (gnu packages admin)
 (gnu packages python)
 (gnu packages python-build)
 (gnu packages python-xyz)
 (gnu packages imagemagick)
 (gnu packages version-control)
 (gnu packages ncurses)
 (guix-janelia packages python-xyz)
 (guix-janelia packages python-janelia))

(define %source-dir (dirname (dirname (dirname (current-filename)))))

(define-public python-dev-package
  (package
    (name "python-dev-package")
    (version "dev")
    (source (local-file %source-dir
                        #:recursive? #t
                        #:select? (git-predicate %source-dir)))
    (build-system python-build-system)
    (native-inputs (list gnu-make
                         git
                         emacs
                         emacs-org
                         emacs-ox-gfm
                         python
                         python-wheel
                         python-twine
                         python-ipython
                         imagemagick
                         nmap))
    (propagated-inputs (list
                        ncurses
                        python-click
                        python-nmap))
    (home-page "")
    (synopsis "")
    (description "")
    (license license:bsd-3)))

python-dev-package
