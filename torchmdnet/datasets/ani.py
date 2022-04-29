import h5py
import numpy as np
import os
import torch as pt
from torch_geometric.data import Data, Dataset, download_url, extract_tar
from tqdm import tqdm


class ANIBase(Dataset):

    HARTREE_TO_EV = 27.211386246

    @property
    def raw_url(self):
        raise NotImplementedError

    @property
    def raw_file_names(self):
        raise NotImplementedError

    @property
    def atomic_numbers(self):
        raise NotImplementedError

    @property
    def atomic_energies(self):
        raise NotImplementedError

    def __init__(self, root, transform=None, pre_transform=None, pre_filter=None, dataset_arg=None):
        self.name = self.__class__.__name__
        super().__init__(root, transform, pre_transform, pre_filter)

        idx_name, z_name, pos_name, y_name = self.processed_paths
        self.idx_mm = np.memmap(idx_name, mode='r', dtype=np.int64)
        self.z_mm = np.memmap(z_name, mode='r', dtype=np.int8)
        self.pos_mm = np.memmap(pos_name, mode='r', dtype=np.float32, shape=(self.z_mm.shape[0], 3))
        self.y_mm = np.memmap(y_name, mode='r', dtype=np.float64)

        assert self.idx_mm[0] == 0
        assert self.idx_mm[-1] == len(self.z_mm)
        assert len(self.idx_mm) == len(self.y_mm) + 1

    @property
    def processed_file_names(self):
        return [f'{self.name}.idx.mmap', f'{self.name}.z.mmap', f'{self.name}.pos.mmap', f'{self.name}.y.mmap']

    def _sample_iter(self):

        for path in tqdm(self.raw_paths, desc='Files'):
            molecules = list(h5py.File(path).values())[0].values()

            for mol in tqdm(molecules, desc='Molecules', leave=False):
                z = pt.tensor([self.atomic_numbers[atom] for atom in mol['species']], dtype=pt.long)
                all_pos = pt.tensor(mol['coordinates'][:], dtype=pt.float32)
                all_y = pt.tensor(mol['energies'][:] * self.HARTREE_TO_EV, dtype=pt.float64)

                assert all_pos.shape[0] == all_y.shape[0]
                assert all_pos.shape[1] == z.shape[0]
                assert all_pos.shape[2] == 3

                for pos, y in zip(all_pos, all_y):
                    data = Data(z=z, pos=pos, y=y.view(1, 1))

                    if self.pre_filter is not None and not self.pre_filter(data):
                        continue

                    if self.pre_transform is not None:
                        data = self.pre_transform(data)

                    yield data

    def process(self):

        print('Gathering statistics...')
        num_all_confs = 0
        num_all_atoms = 0
        for data in self._sample_iter():
            num_all_confs += 1
            num_all_atoms += data.z.shape[0]

        print(f'  Total number of conformers: {num_all_confs}')
        print(f'  Total number of atoms: {num_all_atoms}')

        idx_name, z_name, pos_name, y_name = self.processed_paths
        idx_mm = np.memmap(idx_name + '.tmp', mode='w+', dtype=np.int64, shape=(num_all_confs + 1,))
        z_mm = np.memmap(z_name + '.tmp', mode='w+', dtype=np.int8, shape=(num_all_atoms,))
        pos_mm = np.memmap(pos_name + '.tmp', mode='w+', dtype=np.float32, shape=(num_all_atoms, 3))
        y_mm = np.memmap(y_name + '.tmp', mode='w+', dtype=np.float64, shape=(num_all_confs,))

        print('Storing data...')
        i_atom = 0
        for i_conf, data in enumerate(self._sample_iter()):
            i_next_atom = i_atom + data.z.shape[0]

            idx_mm[i_conf] = i_atom
            z_mm[i_atom:i_next_atom] = data.z.to(pt.int8)
            pos_mm[i_atom:i_next_atom] = data.pos
            y_mm[i_conf] = data.y

            i_atom = i_next_atom

        idx_mm[-1] = num_all_atoms
        assert i_atom == num_all_atoms

        idx_mm.flush()
        z_mm.flush()
        pos_mm.flush()
        y_mm.flush()

        os.rename(idx_mm.filename, idx_name)
        os.rename(z_mm.filename, z_name)
        os.rename(pos_mm.filename, pos_name)
        os.rename(y_mm.filename, y_name)

    def len(self):
        return len(self.y_mm)

    def get(self, idx):

        atoms = slice(self.idx_mm[idx], self.idx_mm[idx+1])
        z = pt.tensor(self.z_mm[atoms], dtype=pt.long)
        pos = pt.tensor(self.pos_mm[atoms], dtype=pt.float32)
        y = pt.tensor(self.y_mm[idx], dtype=pt.float32).view(1, 1) # It would be better to use float64, but the trainer complaints

        return Data(z=z, pos=pos, y=y)

    def get_atomref(self, max_z=100):

        out = pt.zeros(max_z)
        out[list(self.atomic_numbers.values())] = pt.tensor(list(self.atomic_energies.values()))

        return out.view(-1, 1)


class ANI1(ANIBase):

    @property
    def raw_url(self):
        return 'https://ndownloader.figshare.com/files/9057631'

    @property
    def raw_file_names(self):
        return [os.path.join('ANI-1_release', f'ani_gdb_s{i:02d}.h5') for i in range(1, 9)]

    def download(self):
        archive = download_url(self.raw_url, self.raw_dir)
        extract_tar(archive, self.raw_dir)
        os.remove(archive)

    @property
    def atomic_numbers(self):
        return {
            b'H': 1,
            b'C': 6,
            b'N': 7,
            b'O': 8
        }

    @property
    def atomic_energies(self):
        return {
            'H': -0.500607632585 * self.HARTREE_TO_EV,
            'C': -37.8302333826 * self.HARTREE_TO_EV,
            'N': -54.5680045287 * self.HARTREE_TO_EV,
            'O': -75.0362229210 * self.HARTREE_TO_EV
        }

    # Circumvent https://github.com/pyg-team/pytorch_geometric/issues/4567
    # TODO remove when fixed
    def download(self):
        super().download()

    # Circumvent https://github.com/pyg-team/pytorch_geometric/issues/4567
    # TODO remove when fixed
    def process(self):
        super().process()


class ANI1X(ANIBase):

    @property
    def raw_url(self):
        return 'https://figshare.com/ndownloader/files/18112775'

    @property
    def raw_file_names(self):
        return 'ani1x-release.h5'

    def download(self):
        file = download_url(self.raw_url, self.raw_dir)
        assert len(self.raw_paths) == 1
        os.rename(file, self.raw_paths[0])

    @property
    def atomic_numbers(self):
        return {
            b'H': 1,
            b'C': 6,
            b'N': 7,
            b'O': 8
        }

    @property
    def atomic_energies(self):
        return {
            'H': -0.500607632585 * self.HARTREE_TO_EV,
            'C': -37.8302333826 * self.HARTREE_TO_EV,
            'N': -54.5680045287 * self.HARTREE_TO_EV,
            'O': -75.0362229210 * self.HARTREE_TO_EV
        }

    def _sample_iter(self):

        assert len(self.raw_paths) == 1

        with h5py.File(self.raw_paths[0]) as h5:
            for mol in tqdm(h5.values(), desc='Molecules'):

                z = pt.tensor(mol['atomic_numbers'][:], dtype=pt.long)
                all_pos = pt.tensor(mol['coordinates'][:], dtype=pt.float32)
                all_y = pt.tensor(mol['wb97x_dz.energy'][:] * self.HARTREE_TO_EV, dtype=pt.float64)
                all_dy = pt.tensor(mol['wb97x_dz.forces'][:] * self.HARTREE_TO_EV, dtype=pt.float32)

                assert all_pos.shape[0] == all_y.shape[0]
                assert all_pos.shape[1] == z.shape[0]
                assert all_pos.shape[2] == 3

                assert all_dy.shape[0] == all_y.shape[0]
                assert all_dy.shape[1] == z.shape[0]
                assert all_dy.shape[2] == 3

                for pos, y, dy in zip(all_pos, all_y, all_dy):

                    if y.isnan() or dy.isnan().any():
                        continue

                    data = Data(z=z, pos=pos, y=y.view(1, 1), dy=dy)

                    if self.pre_filter is not None and not self.pre_filter(data):
                        continue

                    if self.pre_transform is not None:
                        data = self.pre_transform(data)

                    yield data

    # Circumvent https://github.com/pyg-team/pytorch_geometric/issues/4567
    # TODO remove when fixed
    def process(self):
        super().process()

    # Circumvent https://github.com/pyg-team/pytorch_geometric/issues/4567
    # TODO remove when fixed
    def process(self):
        super().process()