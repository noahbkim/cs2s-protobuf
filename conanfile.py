from conan import ConanFile
from conan.errors import ConanInvalidConfiguration
from conan.tools.cmake import CMake, CMakeDeps, CMakeToolchain, cmake_layout
from conan.tools.files import copy, rename, get, apply_conandata_patches, replace_in_file, rmdir, rm
from conan.tools.microsoft import check_min_vs, msvc_runtime_flag, is_msvc
from conan.tools.scm import Version

import os
import textwrap

required_conan_version = ">=1.53"


class ProtobufConan(ConanFile):
    name = "protobuf"
    version = "3.21.8"
    description = "Protocol Buffers - Google's data interchange format configured for Counter-Strike 2"
    topics = ("protocol-buffers", "protocol-compiler", "serialization", "rpc", "protocol-compiler", "cs2", "cs2s")
    url = "https://github.com/noahbkim/cs2s-protobuf"
    homepage = "https://github.com/protocolbuffers/protobuf"
    license = "BSD-3-Clause"
    package_type = "library"
    settings = "os", "arch", "compiler", "build_type"
    options = {
        "shared": [True, False],
        "fPIC": [True, False],
        "with_rtti": [True, False],
        "lite": [True, False],
        "debug_suffix": [True, False],
    }
    default_options = {
        "shared": False,
        "fPIC": True,
        "with_rtti": True,
        "lite": False,
        "debug_suffix": True,
    }

    short_paths = True

    # Copy these files and subdirectories manually for build
    exports_sources = "CMakeLists.txt", "configure.ac", "src*", "cmake*", "third_party*"

    @property
    def _is_clang_cl(self):
        return self.settings.compiler == "clang" and self.settings.os == "Windows"

    @property
    def _is_clang_x86(self):
        return self.settings.compiler == "clang" and self.settings.arch == "x86"

    def validate(self):
        check_min_vs(self, "190")

        if self.settings.compiler == "clang":
            if Version(self.settings.compiler.version) < "4":
                raise ConanInvalidConfiguration(f"{self.ref} doesn't support clang < 4")

    @property
    def _cmake_install_base_path(self):
        return os.path.join("lib", "cmake", "protobuf")

    def generate(self):
        tc = CMakeToolchain(self)
        tc.cache_variables["CMAKE_INSTALL_CMAKEDIR"] = self._cmake_install_base_path.replace("\\", "/")
        tc.cache_variables["protobuf_BUILD_TESTS"] = False
        tc.cache_variables["protobuf_BUILD_PROTOC_BINARIES"] = self.settings.os != "tvOS"
        if not self.options.debug_suffix:
            tc.cache_variables["protobuf_DEBUG_POSTFIX"] = ""
        tc.cache_variables["protobuf_BUILD_LIBPROTOC"] = self.settings.os != "tvOS"
        tc.cache_variables["protobuf_DISABLE_RTTI"] = not self.options.with_rtti
        if is_msvc(self) or self._is_clang_cl:
            runtime = msvc_runtime_flag(self)
            if not runtime:
                runtime = self.settings.get_safe("compiler.runtime")
            tc.cache_variables["protobuf_MSVC_STATIC_RUNTIME"] = "MT" in runtime
        tc.generate()

        deps = CMakeDeps(self)
        deps.generate()

    def _patch_sources(self):
        # Provide relocatable protobuf::protoc target and Protobuf_PROTOC_EXECUTABLE cache variable
        # TODO: some of the following logic might be disabled when conan will
        #       allow to create executable imported targets in package_info()
        protobuf_config_cmake = os.path.join(self.source_folder, "cmake", "protobuf-config.cmake.in")

        exe_ext = ".exe" if self.settings.os == "Windows" else ""
        protoc_filename = "protoc" + exe_ext
        module_folder_depth = len(os.path.normpath(self._cmake_install_base_path).split(os.path.sep))
        protoc_rel_path = "{}bin/{}".format("".join(["../"] * module_folder_depth), protoc_filename)
        protoc_target = textwrap.dedent("""\
            if(NOT TARGET protobuf::protoc)
                if(CMAKE_CROSSCOMPILING)
                    find_program(PROTOC_PROGRAM protoc PATHS ENV PATH NO_DEFAULT_PATH)
                endif()
                if(NOT PROTOC_PROGRAM)
                    set(PROTOC_PROGRAM \"${{CMAKE_CURRENT_LIST_DIR}}/{protoc_rel_path}\")
                endif()
                get_filename_component(PROTOC_PROGRAM \"${{PROTOC_PROGRAM}}\" ABSOLUTE)
                set(Protobuf_PROTOC_EXECUTABLE ${{PROTOC_PROGRAM}} CACHE FILEPATH \"The protoc compiler\")
                add_executable(protobuf::protoc IMPORTED)
                set_property(TARGET protobuf::protoc PROPERTY IMPORTED_LOCATION ${{Protobuf_PROTOC_EXECUTABLE}})
            endif()
        """.format(protoc_rel_path=protoc_rel_path))
        replace_in_file(self,
            protobuf_config_cmake,
            "include(\"${CMAKE_CURRENT_LIST_DIR}/protobuf-targets.cmake\")",
            protoc_target
        )

    def build(self):
        self._patch_sources()
        cmake = CMake(self)
        cmake.configure()
        cmake.build()

    def package(self):
        copy(self, "LICENSE", src=self.source_folder, dst=os.path.join(self.package_folder, "licenses"))
        cmake = CMake(self)
        cmake.install()
        rmdir(self, os.path.join(self.package_folder, "lib", "pkgconfig"))
        os.unlink(os.path.join(self.package_folder, self._cmake_install_base_path, "protobuf-config-version.cmake"))
        os.unlink(os.path.join(self.package_folder, self._cmake_install_base_path, "protobuf-targets.cmake"))
        os.unlink(os.path.join(self.package_folder, self._cmake_install_base_path, "protobuf-targets-{}.cmake".format(str(self.settings.build_type).lower())))
        rename(self, os.path.join(self.package_folder, self._cmake_install_base_path, "protobuf-config.cmake"),
                     os.path.join(self.package_folder, self._cmake_install_base_path, "protobuf-generate.cmake"))

        if not self.options.lite:
            rm(self, "libprotobuf-lite*", os.path.join(self.package_folder, "lib"))
            rm(self, "libprotobuf-lite*", os.path.join(self.package_folder, "bin"))

    def package_info(self):
        self.cpp_info.set_property("cmake_find_mode", "both")
        self.cpp_info.set_property("cmake_module_file_name", "Protobuf")
        self.cpp_info.set_property("cmake_file_name", "protobuf")
        self.cpp_info.set_property("pkg_config_name", "protobuf_full_package") # unofficial, but required to avoid side effects (libprotobuf component "steals" the default global pkg_config name)

        build_modules = [
            os.path.join(self._cmake_install_base_path, "protobuf-generate.cmake"),
            os.path.join(self._cmake_install_base_path, "protobuf-module.cmake"),
            os.path.join(self._cmake_install_base_path, "protobuf-options.cmake"),
        ]
        self.cpp_info.set_property("cmake_build_modules", build_modules)

        lib_prefix = "lib" if (is_msvc(self) or self._is_clang_cl) else ""
        lib_suffix = "d" if self.settings.build_type == "Debug" and self.options.debug_suffix else ""

        # libprotobuf
        self.cpp_info.components["libprotobuf"].set_property("cmake_target_name", "protobuf::libprotobuf")
        self.cpp_info.components["libprotobuf"].set_property("pkg_config_name", "protobuf")
        self.cpp_info.components["libprotobuf"].builddirs.append(self._cmake_install_base_path)
        self.cpp_info.components["libprotobuf"].libs = [lib_prefix + "protobuf" + lib_suffix]
        if self.settings.os in ["Linux", "FreeBSD"]:
            self.cpp_info.components["libprotobuf"].system_libs.extend(["m", "pthread"])
            if self._is_clang_x86 or "arm" in str(self.settings.arch):
                self.cpp_info.components["libprotobuf"].system_libs.append("atomic")
        if self.settings.os == "Android":
            self.cpp_info.components["libprotobuf"].system_libs.append("log")
        if self.settings.compiler == "gcc":
            self.cpp_info.components["libprotobuf"].defines.append("_GLIBCXX_USE_CXX11_ABI=0")

        # libprotoc
        if self.settings.os != "tvOS":
            self.cpp_info.components["libprotoc"].set_property("cmake_target_name", "protobuf::libprotoc")
            self.cpp_info.components["libprotoc"].libs = [lib_prefix + "protoc" + lib_suffix]
            self.cpp_info.components["libprotoc"].requires = ["libprotobuf"]
            if self.settings.compiler == "gcc":
                self.cpp_info.components["libprotoc"].defines.append("_GLIBCXX_USE_CXX11_ABI=0")

        # libprotobuf-lite
        if self.options.lite:
            self.cpp_info.components["libprotobuf-lite"].set_property("cmake_target_name", "protobuf::libprotobuf-lite")
            self.cpp_info.components["libprotobuf-lite"].set_property("pkg_config_name", "protobuf-lite")
            self.cpp_info.components["libprotobuf-lite"].builddirs.append(self._cmake_install_base_path)
            self.cpp_info.components["libprotobuf-lite"].libs = [lib_prefix + "protobuf-lite" + lib_suffix]
            if self.settings.os in ["Linux", "FreeBSD"]:
                self.cpp_info.components["libprotobuf-lite"].system_libs.extend(["m", "pthread"])
                if self._is_clang_x86 or "arm" in str(self.settings.arch):
                    self.cpp_info.components["libprotobuf-lite"].system_libs.append("atomic")
            if self.settings.os == "Android":
                self.cpp_info.components["libprotobuf-lite"].system_libs.append("log")
            if self.settings.compiler == "gcc":
                self.cpp_info.components["libprotobuf-lite"].defines.append("_GLIBCXX_USE_CXX11_ABI=0")

        # TODO: to remove in conan v2 once cmake_find_package* & pkg_config generators removed
        self.cpp_info.filenames["cmake_find_package"] = "Protobuf"
        self.cpp_info.filenames["cmake_find_package_multi"] = "protobuf"
        self.cpp_info.names["pkg_config"] ="protobuf_full_package"
        for generator in ["cmake_find_package", "cmake_find_package_multi"]:
            self.cpp_info.components["libprotobuf"].build_modules[generator] = build_modules
        if self.options.lite:
            for generator in ["cmake_find_package", "cmake_find_package_multi"]:
                self.cpp_info.components["libprotobuf-lite"].build_modules[generator] = build_modules
        self.env_info.PATH.append(os.path.join(self.package_folder, "bin"))
