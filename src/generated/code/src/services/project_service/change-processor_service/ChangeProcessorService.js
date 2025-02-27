
import StorageService from '../storage_service/StorageService';
import ProjectService from '../ProjectService';
import LineParser from '../../line_parser/LineParser';

/**
 * ChangeProcessorService class
 * Responsible for processing changes in the project content
 * so that the project structure remains in sync with the source.
 */
class ChangeProcessorService {
  /**
   * Process method
   * Makes certain that the project service remains in sync when the user performs edits.
   * @param {Array} changes - An array of changes made in the editor.
   * @param {Object} editor - The current value of the editor.
   */
  static process(changes, editor) {
    ProjectService.content = editor.getValue();
    const model = editor.getModel();

    changes.forEach(change => {
      const lines = change.text.split('\n');
      let curLine = change.range.startLineNumber - 1;
      let lineEnd = change.range.endLineNumber - 1;
      let lineIdx = 0;

      // First replace lines that are overwritten. Change can contain only part of line so get full line
      if (change.text.length > 0 || (change.rangeLength > 0 && curLine === lineEnd)) { // when rangeLength on same line with no text: chars removed
        while (lineIdx < lines.length && curLine <= lineEnd) {
          LineParser.parse(model.getLineContent(curLine + 1), curLine);
          lineIdx += 1;
          curLine += 1;
        }
      }

      // Now there are either lines to delete or to insert
      while (curLine < lineEnd) {
        LineParser.deleteLine(lineEnd); // need to do in reverse
        lineEnd -= 1;
      }

      if (change.text.length > 0 && change.rangeLength > 0) {

        while (lineIdx < lines.length) {
          LineParser.parse(model.getLineContent(curLine + 1), curLine);
          lineIdx += 1;
          curLine += 1;
        }
      }

      StorageService.markDirty();
    });
  }
}

export default ChangeProcessorService;
