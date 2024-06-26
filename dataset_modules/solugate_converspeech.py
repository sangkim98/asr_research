import os
import multiprocessing as mp
from pathlib import Path
from typing import Tuple

from torch import Tensor
from torch.utils.data import Dataset
from untar_unzip import _extract_tar, _load_waveform
from script_normalization import etri_normalize
from common import(
    SAMPLE_RATE,
    TRAIN_SUBDIR_NAME,
    VALID_SUBDIR_NAME,
)

_DATA_SUBSETS = [
    "broadcast",
    "hobby",
    "dialog",
    "life",
    "weather",
    "economy",
    "play",
    "shopping",
    "all"
]

SUBDIR_GETTER = 100000
INDEX_SUBDIR_GETTER = 1000

def _get_all_scripts(transcript_path, separator):
    new_list = list()
    with open(transcript_path) as f:
        for line in f:
            modified_line = etri_normalize(line.split(separator, 1)[-1].strip())
            if modified_line is not None:
                new_list.append(modified_line)
        return new_list


def _unpack_solugateSpeech(source_path: str | Path, subset_type: str, n_directories_stripped: int=9):
    ext_archive = '.tar'
        
    if subset_type == 'all':
        tar_files = Path(source_path).glob(f"*{ext_archive}*")
    else:
        tar_files = Path(source_path).glob(f"*{subset_type}_*{ext_archive}*")
    
    args = []
    
    for file in tar_files:
        args.append((file.as_posix(), source_path, False, n_directories_stripped))
    
    pool = mp.Pool(min(mp.cpu_count(), len(args)))
    
    pool.starmap(_extract_tar, args, chunksize=1)


def _get_korConverseSpeech_metadata(
    filename: str, dataset_path: str, ext_audio: str, ext_txt: str,
) -> Tuple[str, int, str]:
    subset_type, index = filename.split("_")

    index = int(index)-1

    transcript_file = filename+ext_txt
    audio_file = filename+ext_audio
    subset_subdir = f"{subset_type}_{(index//SUBDIR_GETTER)+1:02d}"
    indexed_dir = f"{(index//INDEX_SUBDIR_GETTER)+1:03d}"
    
    transcript_filepath = os.path.join(dataset_path, subset_subdir, indexed_dir, transcript_file)
    audio_filepath = os.path.join(dataset_path, subset_subdir, indexed_dir, audio_file)

    # Load text
    with open(transcript_filepath) as f:
        transcript = etri_normalize(f.readline().strip())
        if transcript is None:
            # Translation not found
            raise FileNotFoundError(f"Translation not found for {filename}")

    return (
        audio_filepath,
        SAMPLE_RATE,
        transcript,
    )


class SOLUGATESPEECH(Dataset):
    """
    Args:
        root (str or Path): Path to the directory where the dataset is found or downloaded.
        subset_type (str): Type of subset to be trained on.
    """

    _ext_txt = ".txt"
    _ext_audio = ".wav"

    def __init__(
        self,
        root: str | Path,
        training: bool,
        subset_type: str,
    ) -> None:
        self.root = os.fspath(root)
        self.subset_type = subset_type.lower()
        
        if training:
            dataset_path = os.path.join(root, TRAIN_SUBDIR_NAME)
        else:
            dataset_path = os.path.join(root, VALID_SUBDIR_NAME)
            
        self.dataset_path = dataset_path

        assert(self.subset_type in _DATA_SUBSETS)

        _unpack_solugateSpeech(self.dataset_path, self.subset_type)
        
        if self.subset_type == "all":
            audio_files_path = Path(self.dataset_path).rglob("*"+self._ext_audio)
        else:
            audio_files_path = Path(self.dataset_path).rglob(f"{subset_type}_*"+self._ext_audio)
        
        self._walker = []

        for path in audio_files_path:
            with open(path.with_suffix(self._ext_txt)) as f:
                transcript = etri_normalize(f.readline().strip())
                if transcript is not None:
                    self._walker.append(path.stem)                        

    def get_metadata(self, n: int) -> Tuple[str, int, str]:
        """Get metadata for the n-th sample from the dataset. Returns filepath instead of waveform,
        but otherwise returns the same fields as :py:func:`__getitem__`.

        Args:
            n (int): The index of the sample to be loaded

        Returns:
            Tuple of the following items;

            str:
                Path to audio
            int:
                Sample rate
            str:
                Transcript
        """
        file_name = self._walker[n]
        return _get_korConverseSpeech_metadata(file_name, self.dataset_path, self._ext_audio, self._ext_txt)

    def __getitem__(self, n: int) -> Tuple[Tensor, int, str]:
        """Load the n-th sample from the dataset.

        Args:
            n (int): The index of the sample to be loaded

        Returns:
            Tuple of the following items;

            Tensor:
                Waveform
            int:
                Sample rate
            str:
                Transcript
        """
        metadata = self.get_metadata(n)
        waveform = _load_waveform(metadata[0], metadata[1])
        return (waveform, ) + metadata[1:]

    def __len__(self) -> int:
        return len(self._walker)
