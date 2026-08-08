{pkgs}: {
  deps = [
    pkgs.gperf
    pkgs.zlib
    pkgs.openssl
    pkgs.pkg-config
    pkgs.cmake
  ];
}
