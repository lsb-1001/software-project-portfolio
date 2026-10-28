package com.travel.travel.repository;

import com.travel.travel.entity.Reservation;
import jakarta.persistence.LockModeType;
import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface ReservationRepository extends JpaRepository<Reservation, Long> {
  List<Reservation> findByUsername(String username);

  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select r from Reservation r where r.id=:id")
  Optional<Reservation> lockById(@Param("id") Long id);
}
