package com.travel.travel.repository;

import com.travel.travel.entity.Travel;
import jakarta.persistence.LockModeType;
import java.util.*;
import org.springframework.data.jpa.repository.*;
import org.springframework.data.repository.query.Param;

public interface TravelRepository extends JpaRepository<Travel, Long> {
  @Lock(LockModeType.PESSIMISTIC_WRITE)
  @Query("select t from Travel t where t.id=:id")
  Optional<Travel> lockById(@Param("id") Long id);
}
