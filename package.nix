{
  lib,
  pkgs,
  callPackage,
  buildPythonApplication,
  fetchPypi,
  pyctr,
  pycryptodomex,
  pypng,
  tkinter,
  setuptools,
  mfusepy,
  haccrypto,
  stdenv,

  withGUI ? true,
  # this should probably be an option within python
  mountAliases ? true,

}:

buildPythonApplication rec {
  pname = "ninfs";
  version = "2.0";

  src = builtins.path {
    path = ./.;
    name = "ninfs";
    filter =
      path: type:
      !(builtins.elem (baseNameOf path) [
        "build"
        "dist"
        "localtest"
        "__pycache__"
        "v"
        ".git"
        "_build"
        "ninfs.egg-info"
      ]);
  };

  doCheck = false;

  propagatedBuildInputs =
    [
      pyctr
      pycryptodomex
      pypng
      setuptools
      haccrypto
    ]
    ++ lib.optionals (withGUI) [
      tkinter
    ];

  makeWrapperArgs = [ "--prefix PYTHONPATH : ${mfusepy}/${mfusepy.pythonModule.sitePackages}" ];

  preFixup = lib.optionalString (!mountAliases) ''
    rm $out/bin/mount_*
  '';

  postInstall = lib.optionalString (!stdenv.isDarwin) ''
    mkdir -p $out/share/{applications,icons}
    NINFS_USE_NINFS_EXECUTABLE_IN_DESKTOP=1 $out/bin/ninfs --install-desktop-entry $out/share
  '';

  meta = with lib; {
    description = "FUSE filesystem Python scripts for Nintendo console files";
    homepage = "https://github.com/ihaveamac/ninfs";
    license = licenses.mit;
    platforms = platforms.unix;
    mainProgram = "ninfs";
  };
}
