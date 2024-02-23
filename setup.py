# Copyright Universitat Pompeu Fabra 2020-2023  https://www.compscience.org
# Distributed under the MIT License.
# (See accompanying file README.md file or copy at http://opensource.org/licenses/MIT)

from setuptools import setup
import torch
from torch.utils.cpp_extension import (
    BuildExtension,
    CUDAExtension,
    include_paths,
    CppExtension,
)
import versioneer
import os

# If CPU_ONLY is defined
force_cpu_only = os.environ.get("CPU_ONLY", None) is not None
use_cuda = torch.cuda._is_compiled() if not force_cpu_only else False


def set_torch_cuda_arch_list():
    """Set the CUDA arch list according to the architectures the current torch installation was compiled for.
    This function is a no-op if the environment variable TORCH_CUDA_ARCH_LIST is already set or if torch was not compiled with CUDA support.
    """
    if not os.environ.get("TORCH_CUDA_ARCH_LIST"):
        if use_cuda:
            arch_flags = torch._C._cuda_getArchFlags()
            sm_versions = [x[3:] for x in arch_flags.split() if x.startswith("sm_")]
            formatted_versions = ";".join([f"{y[0]}.{y[1]}" for y in sm_versions])
            formatted_versions += "+PTX"
            os.environ["TORCH_CUDA_ARCH_LIST"] = formatted_versions


set_torch_cuda_arch_list()

extension_root = os.path.join("torchmdnet", "extensions")
neighbor_sources = ["neighbors_cpu.cpp"]
if use_cuda:
    neighbor_sources.append("neighbors_cuda.cu")
neighbor_sources = [
    os.path.join(extension_root, "neighbors", source) for source in neighbor_sources
]

ExtensionType = CppExtension if not use_cuda else CUDAExtension
extensions = ExtensionType(
    name="torchmdnet.extensions.torchmdnet_extensions",
    sources=[os.path.join(extension_root, "extensions.cpp")] + neighbor_sources,
    include_dirs=include_paths(),
    define_macros=[("WITH_CUDA", 1)] if use_cuda else [],
)

if __name__ == "__main__":
    buildext = BuildExtension.with_options(no_python_abi_suffix=True, use_ninja=False)
    setup(
        ext_modules=[extensions],
        version=versioneer.get_version(),
        cmdclass=versioneer.get_cmdclass({"build_ext": buildext}),
    )
