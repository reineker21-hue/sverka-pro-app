import ru.slavitsa.sverkapro.core.ReconciliationEngine;
import ru.slavitsa.sverkapro.core.SpreadsheetReader;
import ru.slavitsa.sverkapro.core.TableData;
import ru.slavitsa.sverkapro.core.XlsxReportWriter;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class NativeEngineTest {
    public static void main(String[] args) throws Exception {
        List<List<Object>> firstRows = new ArrayList<>();
        List<List<Object>> secondRows = new ArrayList<>();
        firstRows.add(List.of("Дата", "Документ", "Дебет", "Кредит"));
        secondRows.add(List.of("Дата", "Документ", "Дебет", "Кредит"));
        for (int index = 1; index <= 2500; index++) {
            double amount = 10.0 + index / 100.0;
            firstRows.add(List.of("01.07.26", "Поступление № УТ-" + index + " от 01.07.2026", "", amount));
            secondRows.add(List.of("01.07.26", "Отгрузка 01.07.26 ( №УТ-" + index + ")", amount, ""));
        }
        TableData first = TableData.fromMatrix("first.xlsx", "Лист1", firstRows);
        TableData second = TableData.fromMatrix("second.xls", "Лист1", secondRows);
        long started = System.nanoTime();
        ReconciliationEngine.Result result = ReconciliationEngine.compare(first, second, 0.01);
        double elapsed = (System.nanoTime() - started) / 1_000_000_000.0;
        require(result.differences().isEmpty(), "Неожиданные расхождения");
        require(result.onlyFirst().isEmpty() && result.onlySecond().isEmpty(), "Неожиданные пропуски");
        require(result.matches().size() == 2500, "Ожидалось 2500 совпадений");
        require(elapsed < 8.0, "Сверка медленнее 8 секунд: " + elapsed);

        ByteArrayOutputStream reportBytes = new ByteArrayOutputStream();
        XlsxReportWriter.write(result, reportBytes);
        TableData report = SpreadsheetReader.read(new ByteArrayInputStream(reportBytes.toByteArray()), "report.xlsx");
        require("ИТОГ".equals(report.sheetName), "Excel-отчёт не читается обратно");

        byte[] csv = "Дата;Документ;Дебет;Кредит\n01.07.26;Оплата № 1;;10,50\n".getBytes(StandardCharsets.UTF_8);
        TableData csvTable = SpreadsheetReader.read(new ByteArrayInputStream(csv), "sample.csv");
        require(csvTable.rows.size() == 1, "CSV прочитан неверно");
        System.out.printf("Native engine smoke test OK: 2500+2500 за %.3f сек.%n", elapsed);
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
