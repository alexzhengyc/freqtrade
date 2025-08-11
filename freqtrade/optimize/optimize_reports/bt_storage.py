import logging
from io import BytesIO
from pathlib import Path
from typing import Any

from pandas import DataFrame

from freqtrade.configuration import sanitize_config
from freqtrade.constants import LAST_BT_RESULT_FN
from freqtrade.enums.runmode import RunMode
from freqtrade.ft_types import BacktestResultType
from freqtrade.misc import file_dump_json


logger = logging.getLogger(__name__)


def file_dump_joblib(file_obj: BytesIO, data: Any, log: bool = True) -> None:
    """
    Dump object data into a file
    :param filename: file to create
    :param data: Object data to save
    :return:
    """
    import joblib

    joblib.dump(data, file_obj)


def _generate_filename(recordfilename: Path, appendix: str, suffix: str) -> Path:
    """
    Generates a filename based on the provided parameters.
    :param recordfilename: Path object, which can either be a filename or a directory.
    :param appendix: use for the filename. e.g. backtest-result-<datetime>
    :param suffix: Suffix to use for the file, e.g. .json, .pkl
    :return: Generated filename as a Path object
    """
    if recordfilename.is_dir():
        filename = (recordfilename / f"backtest-result-{appendix}").with_suffix(suffix)
    else:
        filename = Path.joinpath(
            recordfilename.parent, f"{recordfilename.stem}-{appendix}"
        ).with_suffix(suffix)
    return filename


def store_backtest_results(
    config: dict,
    stats: BacktestResultType,
    dtappendix: str,
    *,
    market_change_data: DataFrame | None = None,
    analysis_results: dict[str, dict[str, DataFrame]] | None = None,
    strategy_files: dict[str, str] | None = None,
) -> Path:
    """
    Stores backtest results and analysis data in a folder structure, with metadata stored separately
    for convenience.
    :param config: Configuration dictionary
    :param stats: Dataframe containing the backtesting statistics
    :param dtappendix: Datetime to use for the filename
    :param market_change_data: Dataframe containing market change data
    :param analysis_results: Dictionary containing analysis results
    """
    recordfilename: Path = config["exportfilename"]
    base_filename = _generate_filename(recordfilename, dtappendix, "")

    # Create a folder to store all backtest results
    folder_name = f"backtest-result-{dtappendix}"
    if recordfilename.is_dir():
        results_folder = recordfilename / folder_name
    else:
        results_folder = recordfilename.parent / folder_name

    results_folder.mkdir(parents=True, exist_ok=True)

    # Store metadata separately with .json extension
    metadata_file = results_folder / f"{base_filename.stem}.meta.json"
    file_dump_json(metadata_file, stats["metadata"])

    # Store latest backtest info separately
    latest_filename = results_folder.parent / LAST_BT_RESULT_FN
    file_dump_json(latest_filename, {"latest_backtest": str(results_folder.name)}, log=False)

    # Store stats as JSON file
    stats_copy = {
        "strategy": stats["strategy"],
        "strategy_comparison": stats["strategy_comparison"],
    }
    stats_file = results_folder / f"{base_filename.stem}.json"
    file_dump_json(stats_file, stats_copy)

    # Store config file
    config_file = results_folder / f"{base_filename.stem}_config.json"
    file_dump_json(config_file, sanitize_config(config["original_config"]))

    # Store strategy files and their parameters
    for strategy_name, strategy_file in (strategy_files or {}).items():
        strategy_path = Path(strategy_file)
        if not strategy_path.is_file():
            logger.warning(f"Strategy file '{strategy_path}' does not exist. Skipping.")
            continue

        # Copy strategy file
        strategy_dest = results_folder / f"{base_filename.stem}_{strategy_name}.py"
        strategy_dest.write_bytes(strategy_path.read_bytes())

        # Copy strategy parameters if they exist
        strategy_params = strategy_path.with_suffix(".json")
        if strategy_params.is_file():
            params_dest = results_folder / f"{base_filename.stem}_{strategy_name}.json"
            params_dest.write_bytes(strategy_params.read_bytes())

    # Add market change data if present
    if market_change_data is not None:
        market_change_file = results_folder / f"{base_filename.stem}_market_change.feather"
        market_change_data.reset_index().to_feather(
            market_change_file, compression_level=9, compression="lz4"
        )

    # Add analysis results if present and running in backtest mode
    if (
        config.get("export", "none") == "signals"
        and analysis_results is not None
        and config.get("runmode", RunMode.OTHER) == RunMode.BACKTEST
    ):
        for name in ["signals", "rejected", "exited"]:
            if name in analysis_results:
                analysis_file = results_folder / f"{base_filename.stem}_{name}.pkl"
                analysis_buf = BytesIO()
                file_dump_joblib(analysis_buf, analysis_results[name])
                analysis_file.write_bytes(analysis_buf.getvalue())

    # Generate console markdown and visual analysis files in the same folder
    try:
        from freqtrade.optimize.optimize_reports.bt_output import write_backtest_console_markdown

        console_files = write_backtest_console_markdown(
            config, stats, results_folder=results_folder
        )
        logger.info(f"Generated {len(console_files)} console markdown and visual analysis files")
    except Exception as e:
        logger.warning(f"Failed to generate console markdown and visual analysis: {e}")
        # Don't let this failure prevent the backtest results from being stored

    logger.info(f"Backtest results stored in folder: {results_folder}")
    return results_folder
