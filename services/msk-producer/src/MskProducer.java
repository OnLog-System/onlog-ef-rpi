import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.serialization.StringSerializer;

import java.util.Properties;

public class MskProducer {

    public static void main(String[] args) throws Exception {

        Properties props = new Properties();

        // ===== Bootstrap Servers (ENV) =====
        String bootstrapServers = System.getenv("KAFKA_BOOTSTRAP_SERVERS");
        if (bootstrapServers == null || bootstrapServers.isEmpty()) {
            throw new RuntimeException("KAFKA_BOOTSTRAP_SERVERS is not set");
        }

        props.put(
            ProducerConfig.BOOTSTRAP_SERVERS_CONFIG,
            bootstrapServers
        );
        // ===================================

        // Kafka 기본 설정
        props.put(
            ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(
            ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
            StringSerializer.class.getName()
        );
        props.put(ProducerConfig.ACKS_CONFIG, "all");

        // ===== IAM + TLS =====
        props.put("security.protocol", "SASL_SSL");
        props.put("sasl.mechanism", "AWS_MSK_IAM");

        props.put(
            "sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;"
        );

        props.put(
            "sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler"
        );
        // =====================

        KafkaProducer<String, String> producer =
            new KafkaProducer<>(props);

        Runtime.getRuntime().addShutdownHook(new Thread(producer::close));

        while (true) {
            ProducerRecord<String, String> record =
                new ProducerRecord<>("onlog-test", "hello-from-rpi");

            producer.send(record, (metadata, exception) -> {
                if (exception != null) {
                    exception.printStackTrace();
                } else {
                    System.out.println(
                        "SUCCESS: " +
                        metadata.topic() +
                        " partition=" + metadata.partition() +
                        " offset=" + metadata.offset()
                    );
                }
            });

            producer.flush();
            Thread.sleep(5000);
        }
    }
}
